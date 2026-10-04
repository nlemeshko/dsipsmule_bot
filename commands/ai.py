"""AI entry points with strict new-message gating for Telegram updates."""

import logging
import os
import random
import re
import time
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from services.ai import AIClient, AIError, MAX_AUDIO

logger = logging.getLogger(__name__)
TRANSCRIBE_STATE = "ai_waiting_audio"


def sender_id(update):
    """Anonymous admins use their group's identity, not Telegram's fake bot user."""
    msg = update.message
    if not msg:
        return None
    if msg.sender_chat:
        if (msg.chat.type in {"group", "supergroup"}
                and msg.sender_chat.id == msg.chat_id
                and not getattr(msg, "is_automatic_forward", False)):
            return msg.chat_id
        return None
    user = update.effective_user
    return user.id if user and not user.is_bot else None


class AIRuntime:
    def __init__(self, started_at=None):
        self.started_at = time.time() if started_at is None else started_at
        self.client = AIClient()
        self.seen = OrderedDict()
        self.users = OrderedDict()
        self.groups = OrderedDict()

    def is_new(self, update):
        msg = update.message
        return bool(msg and sender_id(update) is not None
                    and msg.date.timestamp() > self.started_at
                    and 0 <= time.time() - msg.date.timestamp() < 300)

    def claim(self, chat_id, message_id):
        key = (chat_id, message_id)
        if key in self.seen:
            return False
        self.seen[key] = True
        while len(self.seen) > 4096:
            self.seen.popitem(last=False)
        return True

    def throttle(self, kind, identity, delay, *, group=False):
        store = self.groups if group else self.users
        key = (kind, identity)
        now = time.monotonic()
        if now - store.get(key, -float("inf")) < delay:
            return False
        store[key] = now
        store.move_to_end(key)
        while len(store) > 4096:
            store.popitem(last=False)
        return True


def runtime(context):
    if "ai_runtime" not in context.bot_data:
        context.bot_data["ai_runtime"] = AIRuntime()
    return context.bot_data["ai_runtime"]


def allowed_group(chat_id):
    return str(chat_id) in re.split(r"[,\s]+", os.getenv("ALLOWED_GROUP_ID", "").strip())


def permitted(update, context):
    chat = update.effective_chat
    if not chat or (chat.type != "private" and not (chat.type in {"group", "supergroup"} and allowed_group(chat.id))):
        return False
    if getattr(context, "is_miniapp", False):
        return True
    return runtime(context).is_new(update)


async def reply_text(message, text):
    for offset in range(0, len(text), 4000):
        await message.reply_text(text[offset:offset + 4000])


async def answer(update, context, prompt, *, quiet=False):
    if not permitted(update, context):
        return
    state = runtime(context)
    if not state.throttle("text", sender_id(update), 5):
        if not quiet:
            await update.effective_message.reply_text("Подождите 5 секунд перед следующим вопросом.")
        return
    try:
        await reply_text(update.effective_message, await state.client.text(prompt))
    except AIError as exc:
        logger.warning("AI text unavailable: %s", exc)
        if not quiet:
            await update.effective_message.reply_text(str(exc))


async def ask_command(update, context):
    if not permitted(update, context):
        return
    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.effective_message.reply_text("Напишите вопрос: /ask Как подготовиться к выступлению?")
        return
    await answer(update, context, prompt)


async def draw_command(update, context):
    if not permitted(update, context):
        return
    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.effective_message.reply_text("Опишите картинку: /draw Кот с гитарой в золотом свете")
        return
    state = runtime(context)
    if not state.throttle("image", sender_id(update), 30):
        await update.effective_message.reply_text("Подождите 30 секунд перед следующей картинкой.")
        return
    try:
        photo = BytesIO(await state.client.image(prompt))
        photo.name = "ai-image.jpg"
        await update.effective_message.reply_photo(photo=photo, caption=prompt[:1000])
    except AIError as exc:
        await update.effective_message.reply_text(str(exc))


async def transcribe_bytes(update, context, content, filename):
    if not permitted(update, context):
        return
    state = runtime(context)
    if not state.throttle("speech", sender_id(update), 5):
        await update.effective_message.reply_text("Подождите 5 секунд перед следующим аудио.")
        return
    try:
        await reply_text(update.effective_message, "Расшифровка:\n" + await state.client.transcribe(content, filename))
    except AIError as exc:
        await update.effective_message.reply_text(str(exc))


async def transcribe_message(update, context, source=None):
    if not permitted(update, context):
        return
    source = source or update.effective_message
    media = source.voice or source.audio
    if not media:
        await update.effective_message.reply_text("Ответьте командой /transcribe на голосовое или аудиофайл.")
        return
    if not os.getenv("GROQ_API_KEY"):
        await update.effective_message.reply_text("Расшифровка пока не подключена.")
        return
    if (media.file_size or 0) > MAX_AUDIO or (media.duration or 0) > 600:
        await update.effective_message.reply_text("Для расшифровки пришлите аудио до 10 минут и 20 МБ.")
        return
    try:
        file = await context.bot.get_file(media.file_id)
        content = bytes(await file.download_as_bytearray())
    except Exception as exc:
        logger.warning("AI audio download failed: %s", type(exc).__name__)
        await update.effective_message.reply_text("Не удалось скачать аудио. Попробуйте позже.")
        return
    filename = "voice.ogg" if source.voice else Path(getattr(media, "file_name", None) or file.file_path or "audio.ogg").name
    if Path(filename).suffix.lower() == ".oga":
        filename = str(Path(filename).with_suffix(".ogg"))
    await transcribe_bytes(update, context, content, filename)


async def transcribe_command(update, context):
    if not permitted(update, context):
        return
    from commands.callback_handler import user_states
    replied = update.effective_message.reply_to_message
    if replied and (replied.voice or replied.audio):
        await transcribe_message(update, context, replied)
    elif update.effective_chat.type == "private":
        from commands.pole import pole_games
        pole_games.pop(update.effective_user.id, None)
        user_states[update.effective_user.id] = TRANSCRIBE_STATE
        await update.effective_message.reply_text("Пришлите голосовое или аудиофайл для расшифровки — до 10 минут и 20 МБ.")
    else:
        await update.effective_message.reply_text("Ответьте командой /transcribe на голосовое или аудиофайл.")


async def private_audio(update, context):
    from commands.callback_handler import user_states, ANON_STATE
    from commands.fsm_handler import handle_anon_voice, handle_anon_audio
    state = user_states.get(update.effective_user.id)
    if state == ANON_STATE:
        handler = handle_anon_voice if update.effective_message.voice else handle_anon_audio
        await handler(update, context)
    elif state in {None, TRANSCRIBE_STATE}:
        await transcribe_message(update, context)
        if state == TRANSCRIBE_STATE:
            user_states.pop(update.effective_user.id, None)


async def group_message(update, context):
    if update.effective_chat.type not in {"group", "supergroup"} or not os.getenv("GROQ_API_KEY") or not permitted(update, context):
        return
    msg = update.message
    if not msg or not (msg.text or msg.voice) or (msg.text or "").startswith("/"):
        return
    from commands.pole import pole_games
    if any(game.get("chat_id") == msg.chat_id for game in pole_games.values()):
        return
    state = runtime(context)
    if not state.claim(msg.chat_id, msg.message_id):
        return
    if msg.voice:
        await transcribe_message(update, context)
        return
    if not msg.text or random.random() >= 0.10:
        return
    if not state.throttle("text", msg.chat_id, 15, group=True):
        return
    await answer(update, context, msg.text, quiet=True)
