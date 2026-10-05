"""Group voting, final reports and recovery after redeployment."""

import asyncio
import logging
import math
import time
from weakref import WeakValueDictionary

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from services import titles
from commands.fun import identity, safe_command

logger = logging.getLogger(__name__)
_locks = WeakValueDictionary()


def poll_lock(token):
    lock = _locks.get(token)
    if lock is None:
        lock = asyncio.Lock()
        _locks[token] = lock
    return lock


def poll_text(poll):
    counts = titles.counts(poll)
    text = (f"🏆 {titles.CHOICES['legend']} или {titles.CHOICES['bore']}?\nУчастник: {poll['name']}\n"
            f"{titles.CHOICES['legend']}: {counts['legend']} · {titles.CHOICES['bore']}: {counts['bore']}\n")
    if not poll["closed"]:
        return text + f"Осталось {max(1, math.ceil(poll['until'] - time.time()))} сек. Один голос на человека, выбор можно менять."
    result = poll["result"]
    return text + (f"Итог: {titles.CHOICES[result]}!" if result in titles.CHOICES else
                   "Ничья — звание не меняется." if result == "tie" else "Голосов нет — звание не меняется.")


def markup(poll):
    if poll["closed"]:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=f"titles:{poll['token']}:{choice}")
                                  for choice, name in titles.CHOICES.items()]])


def table_text(rows):
    labels = " / ".join(titles.CHOICES.values())
    lines = [f"📜 Общие итоги «{labels}»"]
    for choice, name in titles.CHOICES.items():
        members = [f"• {row['name']} — {row['counts']['legend']} / {row['counts']['bore']}" for _, row in rows if row["choice"] == choice]
        lines.append(f"\n{name}: {len(members)}")
        lines.extend(members or ["Пока никого."])
    lines.append(f"\nЧисла: голоса за варианты «{labels}» в последнем решающем раунде. /titles — вся таблица.")
    return "\n".join(lines)


def split_table(rows):
    text = table_text(rows)
    pieces, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > 3500:
            pieces.append(current)
            current = ""
        current += line
    return pieces + [current]


def track(context, poll):
    context.bot_data.setdefault("title_pending", {})[poll["token"]] = poll["until"] if poll["message_id"] else 0


async def publish(bot, poll):
    message = await bot.send_message(chat_id=poll["chat_id"], text=poll_text(poll), reply_markup=markup(poll),
                                     reply_to_message_id=poll["source_id"], allow_sending_without_reply=True)
    try:
        return await asyncio.to_thread(titles.attach, poll["token"], message.message_id)
    except Exception:
        # An untracked button must never accept votes after an unsuccessful S3 write.
        await bot.edit_message_text(chat_id=poll["chat_id"], message_id=message.message_id,
                                    text="Не удалось сохранить голосование. Бот попробует открыть его позже.", reply_markup=None)
        raise


@safe_command
async def verdict_command(update, context):
    if update.effective_chat.type not in {"group", "supergroup"}:
        await update.effective_message.reply_text("Голосование запускается в разрешённой группе. Таблица — /titles.")
        return
    uid, name = identity(update)
    poll = await asyncio.to_thread(titles.start, update.effective_chat.id, update.effective_message.message_id, uid, name)
    track(context, poll)
    async with poll_lock(poll["token"]):
        poll = await asyncio.to_thread(titles.due, poll["token"])
        if not poll["message_id"]:
            poll = await publish(context.bot, poll)
            track(context, poll)
        else:
            await update.effective_message.reply_text("За тебя уже идёт голосование. Дождёмся итога через 5 минут после его запуска.")


@safe_command
async def titles_command(update, context):
    rows = await asyncio.to_thread(titles.leaderboard)
    for text in split_table(rows):
        await update.effective_message.reply_text(text)


async def titles_callback(update, context):
    from commands.ai import allowed_group
    query, chat, user = update.callback_query, update.effective_chat, update.effective_user
    if not chat or chat.type not in {"group", "supergroup"} or not allowed_group(chat.id) or not user or user.is_bot:
        await query.answer("Голосование доступно только участникам разрешённой группы", show_alert=True)
        return
    try:
        parts = query.data.split(":")
        if len(parts) != 3:
            raise ValueError("Кнопка недоступна")
        async with poll_lock(parts[1]):
            poll = await asyncio.to_thread(titles.vote, parts[1], chat.id, user.id, parts[2])
            track(context, poll)
            await query.answer("Голос сохранён")
            try:
                await context.bot.edit_message_text(chat_id=chat.id, message_id=poll["message_id"],
                                                    text=poll_text(poll), reply_markup=markup(poll))
            except Exception as exc:
                # Delivery failure never changes an already-durable vote into a failure.
                if not isinstance(exc, BadRequest) or "message is not modified" not in str(exc).lower():
                    logger.warning("Title poll display unavailable: %s", type(exc).__name__)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Title poll update failed: %s", type(exc).__name__)
    except Exception as exc:
        logger.warning("Title vote failed: %s", type(exc).__name__)
        await query.answer("Не удалось сохранить голос. Попробуй позже.", show_alert=True)


async def process_pending(application):
    pending = application.bot_data.setdefault("title_pending", {})
    for token, deadline in list(pending.items()):
        if deadline > time.time():
            continue
        try:
            async with poll_lock(token):
                await process_one(application, token)
        except Exception as exc:
            logger.warning("Title poll recovery failed: %s", type(exc).__name__)


async def process_one(application, token):
    from commands.ai import allowed_group
    pending = application.bot_data["title_pending"]
    poll = await asyncio.to_thread(titles.due, token)
    if poll is None:
        pending.pop(token, None)
        return
    if not allowed_group(poll["chat_id"]):
        await asyncio.to_thread(titles.mark_reported, token)
        pending.pop(token, None)
        return
    if not poll["message_id"]:
        poll = await publish(application.bot, poll)
    if poll["closed"]:
        rows = await asyncio.to_thread(titles.leaderboard)
        text = poll_text(poll) + "\n\n" + table_text(rows)
        if len(text) > 4000:
            text = poll_text(poll) + "\n\nОбщая таблица выросла — все участники доступны через /titles."
        try:
            await application.bot.edit_message_text(chat_id=poll["chat_id"], message_id=poll["message_id"],
                                                    text=text, reply_markup=None)
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
        await asyncio.to_thread(titles.mark_reported, token)
        pending.pop(token, None)
    else:
        pending[token] = poll["until"]


async def worker(application):
    while True:
        try:
            if "title_pending" not in application.bot_data:
                application.bot_data["title_pending"] = await asyncio.to_thread(titles.pending)
            await process_pending(application)
        except Exception as exc:
            logger.warning("Title worker unavailable: %s", type(exc).__name__)
        await asyncio.sleep(15)
