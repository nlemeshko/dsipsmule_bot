"""Persistent community jokes for Telegram and Mini App."""

import asyncio
import logging
import math
import time
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from services import fun

logger = logging.getLogger(__name__)


def identity(update):
    message = update.effective_message
    sender = getattr(message, "sender_chat", None)
    if sender:
        return sender.id, getattr(sender, "title", None) or "Участник"
    user = update.effective_user
    return user.id, getattr(user, "first_name", None) or getattr(user, "username", None) or "Участник"


def leave_private_guess(update, context):
    if update.effective_chat.type == "private":
        context.user_data.pop("fun_guess", None)


def safe_command(handler):
    @wraps(handler)
    async def run(update, context):
        from commands.ai import permitted
        if not permitted(update, context):
            return
        if handler.__name__ != "guess_command":
            leave_private_guess(update, context)
        try:
            await handler(update, context)
            context.bot_data["fun_ready"] = True
        except Exception as exc:
            logger.warning("Community command %s failed: %s", handler.__name__, type(exc).__name__)
            await update.effective_message.reply_text("Не удалось загрузить или сохранить данные. Попробуй позже — постоянную карточку заново не выдаю.")
    return run


@safe_command
async def ded_command(update, context):
    result = await asyncio.to_thread(fun.ded_status)
    bar = "■" * (result["anger"] // 10) + "□" * (10 - result["anger"] // 10)
    await update.effective_message.reply_text(
        f"🧓 Общий дедометр\n{bar} {result['anger']}%\n"
        f"Дедом назвали уже {result['count']} раз во всех разрешённых группах.\n"
        "Каждое новое сообщение со словом «дед» добавляет 10%. На 100% дед взрывается; потом начинается новый круг.")


async def ambient_ded(update, context):
    from commands.ai import runtime
    msg = update.message
    if not fun.DED_PATTERN.search(msg.text) or not runtime(context).claim(msg.chat_id, msg.message_id, kind="ded"):
        return False
    try:
        count = await asyncio.to_thread(fun.mention_ded, msg.chat_id, msg.message_id)
    except Exception as exc:
        logger.warning("Ded counter could not be saved: %s", type(exc).__name__)
        return False
    if count and count % 10 == 0:
        await msg.reply_text("🧓 Дедометр: 100%!\nЕщё раз назовёте дедом — запишу на весь сквад дисс, и автотюн вас уже не спасёт.")
        return True
    return False


async def card_command(update, kind):
    uid, name = identity(update)
    card = await asyncio.to_thread(fun.permanent_card, uid, name, kind)
    heading = "🪪 Паспорт сквада" if kind == "passport" else "🎖 Постоянный орден"
    await update.effective_message.reply_text(
        f"{heading} №{card['number']}\nВладелец: {card['name']}\n"
        f"{card['title']}\n{card['detail']}\nВыдан: {card['issued']}\n"
        "Выдан один раз. Ник меняется — документ остаётся.")


@safe_command
async def passport_command(update, context):
    await card_command(update, "passport")


@safe_command
async def order_command(update, context):
    await card_command(update, "order")


def mood_markup(mood):
    return InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=f"fun:mood:{mood['token']}:{mode}")]
                                 for mode, (name, _) in fun.MOODS.items()])


async def show_mood(message, mood):
    lines = ["🎭 Общее настроение Ведьмака", f"Сейчас: {fun.MOODS[mood['mode']][0]}",
             f"До конца раунда: {max(1, int((mood['until'] - time.time()) / 60))} мин."]
    lines += [f"{name}: {mood['counts'][mode]} голосов" for mode, (name, _) in fun.MOODS.items()]
    lines.append("Один голос на участника во всех чатах. Можно поменять свой выбор. Настроение меняется по лидеру голосования.")
    await message.reply_text("\n".join(lines), reply_markup=mood_markup(mood))


@safe_command
async def mood_command(update, context):
    mood = await asyncio.to_thread(fun.open_mood)
    fun.invalidate_mood()
    await show_mood(update.effective_message, mood)


def guess_markup(chat_id, game):
    prefix = f"fun:guess:{chat_id}:{game['token']}"
    return InlineKeyboardMarkup([[InlineKeyboardButton("Подсказка", callback_data=prefix + ":hint"),
                                  InlineKeyboardButton("Сдаться", callback_data=prefix + ":end")]])


@safe_command
async def guess_command(update, context):
    if update.effective_chat.type == "private":
        from commands.callback_handler import user_states
        from commands.pole import pole_games
        user_states.pop(update.effective_user.id, None)
        if pole_games.get(update.effective_user.id, {}).get("chat_id") == update.effective_chat.id:
            pole_games.pop(update.effective_user.id, None)
    game = await asyncio.to_thread(fun.start_guess, update.effective_chat.id)
    context.bot_data.setdefault("fun_games_active", set()).add(update.effective_chat.id)
    if update.effective_chat.type == "private":
        context.user_data["fun_guess"] = True
    await update.effective_message.reply_text(
        f"🎵 Угадай песню по эмодзи\n\n{game['emoji']}\n\n"
        f"Раунд длится 3 минуты. Осталось {max(1, math.ceil(game['until'] - time.time()))} сек.\n"
        "Напиши название песни. В группе можно ответить на эту загадку или начать с «Ответ:».",
        reply_markup=guess_markup(update.effective_chat.id, game))


async def guess_reply(update, context, *, automatic=False):
    """Return whether a chat message was actually a guess, without swallowing normal conversation."""
    from commands.ai import permitted, runtime
    if not permitted(update, context):
        return False
    msg = update.message
    if not msg or not msg.text or msg.text.startswith("/"):
        return False
    try:
        game = await asyncio.to_thread(fun.guess_game, msg.chat_id)
        if not game or game.get("finished"):
            context.bot_data.setdefault("fun_games_active", set()).discard(msg.chat_id)
            leave_private_guess(update, context)
            if not automatic:
                await msg.reply_text("Этот раунд уже завершён. Начни новый — /guess.")
                return True
            return False
        text = msg.text.strip()
        original = msg.reply_to_message
        quiz_reply = bool(original and "Угадай песню по эмодзи" in (original.text or "")
                          and original.from_user and original.from_user.id == context.bot.id)
        if automatic and not (text.lower().startswith("ответ:") or quiz_reply
                              or fun.normalize_answer(text) == fun.normalize_answer(game["answer"])):
            if game["until"] <= time.time():
                context.bot_data.setdefault("fun_games_active", set()).discard(msg.chat_id)
            return False
        if not runtime(context).claim(msg.chat_id, msg.message_id, kind="guess"):
            return True
        if text.lower().startswith("ответ:"):
            text = text.split(":", 1)[1].strip()
        uid, name = identity(update)
        result = await asyncio.to_thread(fun.solve_guess, msg.chat_id, text, uid, name)
        if result["status"] == "won":
            context.bot_data.setdefault("fun_games_active", set()).discard(msg.chat_id)
            leave_private_guess(update, context)
            await msg.reply_text(f"🏆 {name}, угадано! Это «{result['answer']}». Дед нехотя одобряет.")
        elif result["status"] == "expired":
            context.bot_data.setdefault("fun_games_active", set()).discard(msg.chat_id)
            leave_private_guess(update, context)
            await msg.reply_text(f"⌛ Время вышло. Это «{result['answer']}». Новый раунд — /guess.")
        elif result["status"] == "wrong":
            await msg.reply_text("Мимо, Лютик. Попробуй ещё раз.", reply_markup=guess_markup(msg.chat_id, game))
        return True
    except Exception as exc:
        logger.warning("Guess could not be loaded or saved: %s", type(exc).__name__)
        if not automatic:
            await msg.reply_text("Не удалось сохранить результат игры. Попробуй позже.")
        return False


async def fun_callback(update, context):
    from commands.ai import allowed_group
    query = update.callback_query
    chat = update.effective_chat
    if not chat or (chat.type != "private" and not (chat.type in {"group", "supergroup"} and allowed_group(chat.id))):
        await query.answer("Эта группа не разрешена", show_alert=True)
        return
    try:
        parts = query.data.split(":")
        if len(parts) == 4 and parts[:2] == ["fun", "mood"]:
            uid = update.effective_user.id
            mood = await asyncio.to_thread(fun.vote_mood, uid, parts[2], parts[3])
            await query.answer("Голос учтён")
            await show_mood(update.effective_message, mood)
        elif len(parts) == 5 and parts[:2] == ["fun", "guess"] and int(parts[2]) == chat.id:
            game = await asyncio.to_thread(fun.guess_button, chat.id, parts[3], parts[4])
            await query.answer()
            if parts[4] == "hint":
                await update.effective_message.reply_text(f"💡 Подсказка: {game['hint']}", reply_markup=guess_markup(chat.id, game))
            else:
                context.bot_data.setdefault("fun_games_active", set()).discard(chat.id)
                leave_private_guess(update, context)
                await update.effective_message.reply_text(f"🏳 Это «{game['answer']}». Новый раунд — /guess.")
        else:
            await query.answer("Кнопка недоступна", show_alert=True)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        if getattr(context, "is_miniapp", False):
            await update.effective_message.reply_text(str(exc))
    except Exception as exc:
        logger.warning("Community callback failed: %s", type(exc).__name__)
        await query.answer("Не удалось сохранить действие. Попробуй позже.", show_alert=True)
        if getattr(context, "is_miniapp", False):
            await update.effective_message.reply_text("Не удалось сохранить действие. Попробуй позже.")
