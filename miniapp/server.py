"""Serve the Mini App alongside PTB polling on the same asyncio loop."""

import asyncio
import json
import logging
import os
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from aiohttp import web

from miniapp.auth import validate_init_data
from miniapp.bridge import AppBot, AppContext, make_update
from miniapp.locks import user_lock

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
ARTWORK = STATIC.parent.parent / "images"
ARTWORK_NAMES = {"anon.png", "ask.png", "casino.png", "hall.png", "halllist.png", "help.png",
                 "piar.png", "pole.png", "prediction.png", "rate.png",
                 "sing.png", "vote.png"}
MAX_UPLOAD = 20 * 1024 * 1024
PRIMARY_CALLBACKS = {"button1", "button2", "button3", "button4", "button6"}


def app_state(user_id):
    from commands.callback_handler import user_states
    from commands.ai import TRANSCRIBE_STATE
    state = user_states.get(user_id)
    # Telegram-only conversations are not resumed inside the Mini App.
    return None if state == TRANSCRIBE_STATE else state


@dataclass
class Session:
    history: list = field(default_factory=list)
    requests: OrderedDict = field(default_factory=OrderedDict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    counter: int = 0
    touched: float = field(default_factory=time.monotonic)
    last_action: float = 0


class MediaStore:
    def __init__(self):
        self.items = OrderedDict()
        self.size = 0

    def prune(self, incoming=0):
        while self.items:
            _, (_, content, _, created) = next(iter(self.items.items()))
            if self.size + incoming <= 64 * 1024 * 1024 and time.monotonic() - created < 1800:
                break
            self.items.popitem(last=False)
            self.size -= len(content)

    def put(self, user_id, content, mime):
        if len(content) > MAX_UPLOAD:
            raise ValueError("Вложение слишком большое")
        self.prune(len(content))
        key = secrets.token_urlsafe(24)
        self.items[key] = (user_id, content, mime, time.monotonic())
        self.size += len(content)
        return key

    def get(self, user_id, key):
        self.prune()
        item = self.items.get(key)
        if not item or item[0] != user_id:
            raise web.HTTPNotFound()
        return item[1], item[2]


def command_handlers():
    from commands.ask import ask_command
    from commands.ai import draw_command
    from commands.entertainment import random_command, cat_command, meme_command, casino_command
    from commands.hall import hall_command, halllist_command, vote_command
    from commands.help import help_command
    from commands.pole import pole_command
    from commands.prediction import prediction_command
    from commands.fun import ded_command, passport_command, order_command, guess_command, mood_command
    from commands.titles import titles_command
    async def chat_command(update, context):
        await update.effective_message.reply_text("Привет! Напиши сообщение — я на связи.")

    async def app_help_command(update, context):
        await help_command(update, context, miniapp=True)

    return dict(chat=chat_command, ask=ask_command, draw=draw_command,
                random=random_command, cat=cat_command, meme=meme_command,
                casino=casino_command, hall=hall_command, halllist=halllist_command,
                vote=vote_command, help=app_help_command,
                pole=pole_command, prediction=prediction_command, ded=ded_command,
                passport=passport_command, order=order_command, guess=guess_command, mood=mood_command, titles=titles_command)


class MiniAppServer:
    def __init__(self, application, token):
        self.application = application
        self.token = token
        self.sessions = OrderedDict()
        self.media = MediaStore()
        self.commands = command_handlers()
        self.runner = None
        self.app = web.Application(client_max_size=MAX_UPLOAD + 65536, middlewares=[self.guard])
        self.app.add_routes([
            web.get("/", self.index), web.get("/healthz", self.health),
            web.get("/api/bootstrap", self.bootstrap), web.post("/api/action", self.action),
            web.post("/api/upload", self.upload), web.get("/api/media/{key}", self.media_response),
            web.get("/app.js", self.static), web.get("/styles.css", self.static),
            web.get("/assets/{name}", self.artwork),
        ])

    @web.middleware
    async def guard(self, request, handler):
        try:
            if request.path.startswith("/api/"):
                request["user"] = validate_init_data(
                    request.headers.get("X-Telegram-Init-Data", ""), self.token,
                    max_age=int(os.getenv("MINI_APP_AUTH_MAX_AGE", "3600")),
                )
            response = await handler(request)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            status = 401 if "user" not in request and request.path.startswith("/api/") else 400
            response = web.json_response({"error": str(exc)}, status=status)
        except web.HTTPException as exc:
            response = web.json_response({"error": exc.reason}, status=exc.status)
        except Exception:
            logger.exception("Mini App request failed: %s", request.path)
            response = web.json_response({"error": "Не удалось выполнить действие. Попробуйте позже."}, status=500)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; "
            "img-src 'self' https: blob:; media-src 'self' https: blob:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    def session(self, user_id):
        # Bound memory and expire idle histories; never evict an action in progress.
        for uid, session in list(self.sessions.items()):
            if time.monotonic() - session.touched > 3600 and not session.lock.locked():
                del self.sessions[uid]
        if user_id not in self.sessions:
            if len(self.sessions) >= 512:
                idle = next((uid for uid, s in self.sessions.items() if not s.lock.locked()), None)
                if idle is None:
                    raise web.HTTPServiceUnavailable()
                del self.sessions[idle]
            self.sessions[user_id] = Session(lock=user_lock(user_id))
        session = self.sessions[user_id]
        session.touched = time.monotonic()
        self.sessions.move_to_end(user_id)
        return session

    def result(self, user, session):
        from commands.pole import pole_games
        game = pole_games.get(user["id"], {})
        return {"user": {"first_name": user["first_name"], "username": user.get("username")},
                "messages": session.history, "state": app_state(user["id"]),
                "playing": game.get("chat_id") == user["id"],
                "guessing": bool(self.application.user_data[user["id"]].get("fun_guess"))}

    async def index(self, request):
        return web.FileResponse(STATIC / "index.html")

    async def static(self, request):
        return web.FileResponse(STATIC / request.path.lstrip("/"))

    async def artwork(self, request):
        name = request.match_info["name"]
        if name not in ARTWORK_NAMES:
            raise web.HTTPNotFound()
        return web.FileResponse(ARTWORK / name)

    async def health(self, request):
        return web.json_response({"ok": True})

    async def bootstrap(self, request):
        user = request["user"]
        session = self.session(user["id"])
        async with session.lock:
            return web.json_response(self.result(user, session))

    async def media_response(self, request):
        content, mime = self.media.get(request["user"]["id"], request.match_info["key"])
        return web.Response(body=content, content_type=mime)

    async def action(self, request):
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Ожидается объект действия")
        return await self.execute(request["user"], body)

    async def upload(self, request):
        reader = await request.multipart()
        body, content, filename, mime = {}, bytearray(), "", ""
        async for part in reader:
            if part.name == "file":
                if filename:
                    raise ValueError("Пришлите одно вложение")
                filename = Path(part.filename or "attachment").name
                mime = part.headers.get("Content-Type", "")
                while chunk := await part.read_chunk():
                    content.extend(chunk)
                    if len(content) > MAX_UPLOAD:
                        raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD, actual_size=len(content))
            elif part.name in {"text", "kind", "request_id"}:
                data = await part.read(decode=False)
                if len(data) > 16384:
                    raise ValueError("Слишком длинное поле")
                body[part.name] = data.decode("utf-8")
            else:
                raise ValueError("Неизвестное поле")
        kind = body.get("kind")
        if not content or kind not in {"photo", "voice", "audio"}:
            raise ValueError("Выберите фото или аудио")
        if kind == "photo" and (not mime.startswith("image/") or len(content) > 10 * 1024 * 1024):
            raise ValueError("Фото должно быть не больше 10 МБ")
        if kind != "photo" and not mime.startswith("audio/"):
            raise ValueError("Выберите аудиофайл")
        stream = BytesIO(content)
        stream.name = filename
        body["action"] = "message"
        return await self.execute(request["user"], body, (kind, stream))

    async def execute(self, user, body, upload=None):
        from commands.callback_handler import handle_callback_query, user_states, ANON_STATE
        from commands.fsm_handler import handle_fsm_message, handle_anon_photo, handle_anon_voice, handle_anon_audio
        from commands.message_handler import handle_personal_message
        from commands.pole import handle_pole_message, pole_games

        action = body.get("action")
        text = body.get("text", "")
        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise ValueError("Нет идентификатора действия")
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError("Текст должен быть не длиннее 4000 символов")
        if action not in {"command", "callback", "message", "reset"}:
            raise ValueError("Неизвестное действие")
        session = self.session(user["id"])
        async with session.lock:
            if request_id in session.requests:
                return web.json_response(self.result(user, session))
            if time.monotonic() - session.last_action < 0.6:
                raise web.HTTPTooManyRequests(reason="Подождите секунду перед следующим действием")
            bot = AppBot(self.application.bot, user, session, self.media)
            context = AppContext(self.application, bot, user["id"])
            attachment = None
            user_entry = None
            if upload:
                kind, stream = upload
                state = user_states.get(user["id"])
                if state != ANON_STATE:
                    raise ValueError("В этом шаге вложение не требуется")
                session.requests[request_id] = True
                while len(session.requests) > 100:
                    session.requests.popitem(last=False)
                session.last_action = time.monotonic()
                # Telegram registers file_id for existing moderation and S3 workflows.
                attachment = await getattr(self.application.bot, f"send_{kind}")(
                    chat_id=user["id"], **{kind: stream}, caption=text[:1024] or None,
                )
            if action == "command":
                command = body.get("command")
                if not isinstance(command, str) or command not in self.commands:
                    raise ValueError("Неизвестная команда")
                if command in {"ask", "draw", "hall", "vote"} and not text.strip():
                    raise ValueError("Заполните поле")
                user_states.pop(user["id"], None)
                if command != "guess":
                    context.user_data.pop("fun_guess", None)
                if command != "pole" and pole_games.get(user["id"], {}).get("chat_id") == user["id"]:
                    pole_games.pop(user["id"], None)
                update = make_update(bot, f"/{command} {text}".strip())
                context.args = text.split()
                handler = self.commands[command]
                if command == "pole" and pole_games.get(user["id"], {}).get("chat_id") == user["id"]:
                    handler = None
            elif action == "callback":
                callback = body.get("callback")
                offered = {b.get("callback") for m in session.history for row in m.get("buttons", []) for b in row}
                if not isinstance(callback, str) or callback not in PRIMARY_CALLBACKS | (offered - {None}):
                    raise ValueError("Эта кнопка недоступна")
                if callback in PRIMARY_CALLBACKS:
                    user_states.pop(user["id"], None)
                    context.user_data.pop("fun_guess", None)
                    if pole_games.get(user["id"], {}).get("chat_id") == user["id"]:
                        pole_games.pop(user["id"], None)
                update = make_update(bot, callback=callback)
                if callback.startswith("fun:"):
                    from commands.fun import fun_callback
                    handler = fun_callback
                else:
                    handler = handle_callback_query
            elif action == "reset":
                user_states.pop(user["id"], None)
                context.user_data.pop("fun_guess", None)
                if pole_games.get(user["id"], {}).get("chat_id") == user["id"]:
                    pole_games.pop(user["id"], None)
                session.history.clear()
                handler = None
            else:
                if not text.strip() and not attachment:
                    raise ValueError("Введите текст или выберите файл")
                update = make_update(bot, text, attachment=attachment)
                if text and not attachment:
                    user_entry = {"id": -update.effective_message.message_id, "kind": "text", "text": text, "author": "user"}
                if attachment:
                    handler = {"photo": handle_anon_photo, "voice": handle_anon_voice, "audio": handle_anon_audio}[upload[0]]
                elif app_state(user["id"]):
                    handler = handle_fsm_message
                elif pole_games.get(user["id"], {}).get("chat_id") == user["id"]:
                    handler = handle_pole_message
                elif context.user_data.get("fun_guess"):
                    from commands.fun import guess_reply
                    handler = guess_reply
                else:
                    handler = handle_personal_message
            # Each accepted action replaces the visible result, retaining FSM/game state.
            # Reopening an active game has no handler and keeps its current result.
            if handler:
                session.history.clear()
            if user_entry:
                session.history.append(user_entry)
            # Record before running side effects: transport retries never send moderation twice.
            session.requests[request_id] = True
            while len(session.requests) > 100:
                session.requests.popitem(last=False)
            session.last_action = time.monotonic()
            if handler:
                try:
                    await handler(update, context)
                except Exception:
                    logger.exception("Mini App action failed for user %s", user["id"])
                    await bot.send_message(user["id"], "Не удалось завершить действие. Проверьте результат перед повторной отправкой.")
            session.touched = time.monotonic()
            return web.json_response(self.result(user, session))

    async def start(self):
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, os.getenv("MINI_APP_HOST", "0.0.0.0"), int(os.getenv("MINI_APP_PORT", "8080"))).start()

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
