"""Run existing command handlers, displaying their private replies in the app.

Other recipients and moderation notifications still use the real Telegram bot.
Only server-created Telegram Updates are accepted, never client-supplied Updates.
"""

import mimetypes
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from telegram import Message, Update


class AppBot:
    def __init__(self, real_bot, user: dict, session, media_store):
        self.delivery_bot = real_bot
        self.user = {key: user[key] for key in ("id", "first_name", "last_name", "username", "language_code") if key in user}
        self.user["is_bot"] = False
        self.session = session
        self.media_store = media_store

    def __getattr__(self, name):
        return getattr(self.delivery_bot, name)

    def message(self, text="", **extra):
        self.session.counter += 1
        return Message.de_json({
            "message_id": self.session.counter, "date": int(time.time()),
            "chat": {"id": self.user["id"], "type": "private"},
            "from": self.user, "text": text, **extra,
        }, self)

    async def _send(self, method, chat_id, text="", media=None, kind=None, **kwargs):
        if chat_id != self.user["id"]:
            if kind:
                kwargs[kind] = media
                kwargs["caption"] = text
            else:
                kwargs["text"] = text
            return await getattr(self.delivery_bot, method)(chat_id=chat_id, **kwargs)
        message = self.message(text)
        entry = {"id": message.message_id, "text": text or "", "kind": kind or "text"}
        if media is not None:
            if isinstance(media, str) and (urlsplit(media).scheme in {"https", "http"} or media.startswith("//")):
                # Upstream cover URLs may use HTTP or omit the scheme. The app uses HTTPS.
                entry["url"] = "https:" + media if media.startswith("//") else "https://" + media.split("://", 1)[1]
            else:
                filename = getattr(media, "name", "")
                if isinstance(media, str):
                    file = await self.delivery_bot.get_file(media)
                    content = bytes(await file.download_as_bytearray())
                    filename = file.file_path or ""
                elif isinstance(media, bytes):
                    content = media
                elif hasattr(media, "read"):
                    content = media.read()
                else:
                    raise ValueError("Неподдерживаемый формат вложения")
                mime = mimetypes.guess_type(filename)[0] or ("image/jpeg" if kind == "photo" else "audio/mpeg")
                entry["media"] = self.media_store.put(self.user["id"], content, mime)
        markup = kwargs.get("reply_markup")
        if markup and hasattr(markup, "inline_keyboard"):
            entry["buttons"] = [
                [{"text": b.text, "callback": b.callback_data, "url": b.url} for b in row]
                for row in markup.inline_keyboard
            ]
        # Display text as plain text in the client; never trust Telegram HTML as browser HTML.
        mode = kwargs.get("parse_mode")
        entry["parse_mode"] = getattr(mode, "value", mode)
        self.session.history.append(entry)
        self.session.history[:] = self.session.history[-60:]
        return message

    async def send_message(self, chat_id, text, **kwargs):
        return await self._send("send_message", chat_id, text, **kwargs)

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        return await self._send("send_photo", chat_id, caption, photo, "photo", **kwargs)

    async def send_voice(self, chat_id, voice, caption=None, **kwargs):
        return await self._send("send_voice", chat_id, caption, voice, "voice", **kwargs)

    async def send_audio(self, chat_id, audio, caption=None, **kwargs):
        return await self._send("send_audio", chat_id, caption, audio, "audio", **kwargs)

    async def delete_message(self, chat_id, message_id, **kwargs):
        if chat_id != self.user["id"]:
            return await self.delivery_bot.delete_message(chat_id, message_id, **kwargs)
        self.session.history[:] = [m for m in self.session.history if m["id"] != message_id]
        return True

    async def answer_callback_query(self, *args, **kwargs):
        return True


class AppContext:
    is_miniapp = True

    def __init__(self, application, bot, user_id):
        self.bot = bot
        self.user_data = application.user_data[user_id]
        self.bot_data = application.bot_data
        self.args = []


def make_update(bot: AppBot, text="", callback=None, target=None, attachment=None):
    message = bot.message(text)
    if target:
        replied = bot.message(target, **{"from": {**bot.user, "first_name": target, "last_name": ""}})
        message = bot.message(text, reply_to_message=replied.to_dict())
    if attachment:
        # Media was uploaded by this authenticated user and registered by Telegram.
        message = Message(
            message_id=message.message_id, date=datetime.now(timezone.utc),
            chat=message.chat, from_user=message.from_user,
            photo=attachment.photo, voice=attachment.voice, audio=attachment.audio,
            caption=text or None,
        )
        message.set_bot(bot)
    if callback:
        update = Update.de_json({
            "update_id": bot.session.counter,
            "callback_query": {
                "id": "miniapp", "from": bot.user, "chat_instance": "miniapp",
                "data": callback, "message": message.to_dict(),
            },
        }, bot)
    else:
        update = Update(bot.session.counter, message=message)
    update.set_bot(bot)
    return update
