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
    """Identify anonymous admins and people posting as a channel in a group."""
    msg = update.message
    if not msg:
        return None
    if msg.sender_chat:
        if msg.chat.type in {"group", "supergroup"}:
            if (not getattr(msg, "is_automatic_forward", False)
                    and (msg.sender_chat.id == msg.chat_id
                         or getattr(msg.sender_chat, "type", None) == "channel")):
                return msg.sender_chat.id
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
        return bool(msg
                    and msg.date.timestamp() > self.started_at
                    and 0 <= time.time() - msg.date.timestamp() < 300)

    def claim(self, chat_id, message_id, *, kind=None):
        key = (kind, chat_id, message_id) if kind else (chat_id, message_id)
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


def reply_probability():
    try:
        value = float(os.getenv("AI_REPLY_PROBABILITY", "0.1"))
        if 0 <= value <= 1:
            return value
    except ValueError:
        pass
    logger.warning("Invalid AI_REPLY_PROBABILITY; using 0.1")
    return 0.1


def replied_to_bot(message, bot):
    original = message.reply_to_message
    author = getattr(original, "from_user", None)
    bot_id = getattr(bot, "id", None)
    return bool(author and bot_id is not None and author.id == bot_id)


def replied_to_game(message, bot):
    """Game prompts remain game messages even after a round ends or the bot restarts."""
    if not replied_to_bot(message, bot):
        return False
    original = message.reply_to_message
    text = getattr(original, "text", None) or getattr(original, "caption", None) or ""
    if any(marker in text for marker in (
            "Доступные буквы:", "Игра 'Поле чудес'", "Игра окончена. Чтобы начать новую игру",
            "Угадай песню по эмодзи", "Новый раунд — /guess.")):
        return True
    markup = getattr(original, "reply_markup", None)
    return bool(markup and any(
        (button.callback_data or "").startswith("fun:guess:")
        for row in markup.inline_keyboard for button in row))


def permitted(update, context):
    chat = update.effective_chat
    if not chat or (chat.type != "private" and not (chat.type in {"group", "supergroup"} and allowed_group(chat.id))):
        return False
    if getattr(context, "is_miniapp", False):
        return True
    if not runtime(context).is_new(update):
        return False
    # Every new voice note in an allowed group is eligible, regardless of sender.
    if chat.type in {"group", "supergroup"} and update.message.voice:
        return True
    return sender_id(update) is not None


async def reply_text(message, text):
    for offset in range(0, len(text), 4000):
        await message.reply_text(text[offset:offset + 4000])


async def answer(update, context, prompt, *, quiet=False, rate_limit=True):
    if not permitted(update, context):
        return
    state = runtime(context)
    if rate_limit and not state.throttle("text", sender_id(update), 5):
        if not quiet:
            await update.effective_message.reply_text("Подождите 5 секунд перед следующим вопросом.")
        return
    try:
        instruction = ""
        if context.bot_data.get("fun_ready"):
            from services.fun import mood_instruction
            import asyncio
            try:
                instruction = await asyncio.to_thread(mood_instruction)
            except Exception as exc:
                logger.warning("Mood unavailable: %s", type(exc).__name__)
        if instruction:
            from services.ai import SYSTEM_PROMPT
            text = await state.client.text(prompt, system_prompt=SYSTEM_PROMPT + " Настроение на этот час: " + instruction)
        else:
            text = await state.client.text(prompt)
        await reply_text(update.effective_message, text)
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
    automatic_group_voice = (update.effective_chat.type in {"group", "supergroup"}
                             and update.message and update.message.voice)
    if not automatic_group_voice and not state.throttle("speech", sender_id(update), 5):
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
    if update.effective_chat.type not in {"group", "supergroup"} or not permitted(update, context):
        return
    msg = update.message
    if not msg or not (msg.text or msg.voice):
        return
    state = runtime(context)
    # Voice transcription is independent of games, sender filters and random text replies.
    if msg.voice:
        if not os.getenv("GROQ_API_KEY"):
            return
        if state.claim(msg.chat_id, msg.message_id):
            await transcribe_message(update, context)
        return
    if (msg.text or "").startswith("/"):
        return
    from commands.word_commands import match_word_command, run_word_command
    from commands.pole import pole_games
    pole_active = any(game.get("chat_id") == msg.chat_id for game in pole_games.values())
    guess_active = msg.chat_id in context.bot_data.get("fun_games_active", set())
    game_reply = replied_to_game(msg, context.bot)
    word_command = match_word_command(msg.text)
    if context.bot_data.get("fun_ready") and not (pole_active or guess_active or game_reply):
        from commands.fun import ambient_ded
        if await ambient_ded(update, context) and not word_command:
            from telegram.ext import ApplicationHandlerStop
            state.claim(msg.chat_id, msg.message_id)
            raise ApplicationHandlerStop
    if guess_active:
        from commands.fun import guess_reply
        if await guess_reply(update, context, automatic=True):
            from telegram.ext import ApplicationHandlerStop
            raise ApplicationHandlerStop
    if word_command:
        from telegram.ext import ApplicationHandlerStop
        if state.claim(msg.chat_id, msg.message_id):
            await run_word_command(update, context, word_command)
        # Do not also comment with AI or treat the shortcut as a game guess.
        raise ApplicationHandlerStop
    # Group -1 runs before the pole handler: leave the entire turn to the game,
    # including a winning answer that quotes a bot message.
    if (pole_active or game_reply
            or msg.chat_id in context.bot_data.get("fun_games_active", set())):
        return
    if not os.getenv("GROQ_API_KEY"):
        return
    replying = replied_to_bot(msg, context.bot)
    if replying:
        if not state.claim(msg.chat_id, msg.message_id):
            return
        prompt = msg.text
        original = msg.reply_to_message
        quote = getattr(msg, "quote", None)
        quoted_text = (getattr(quote, "text", None) or getattr(original, "text", None)
                       or getattr(original, "caption", None))
        if quoted_text:
            prompt = ("Твоё предыдущее сообщение (цитата):\n" + quoted_text[:1200]
                      + "\n\nНовое сообщение участника:\n" + msg.text)
        await answer(update, context, prompt, rate_limit=False)
        return
    # Random comments start on standalone posts; other people's reply threads
    # do not invite the bot to continue the conversation.
    if msg.reply_to_message:
        return
    if not state.claim(msg.chat_id, msg.message_id):
        return
    probability = reply_probability()
    if not msg.text or random.random() >= probability:
        return
    if probability < 1 and not state.throttle("text", msg.chat_id, 15, group=True):
        return
    await answer(update, context, msg.text, quiet=True, rate_limit=probability < 1)
