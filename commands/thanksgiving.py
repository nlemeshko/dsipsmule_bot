"""Export contest submissions to the organiser's private Telegram chat."""

import asyncio
import csv
import logging
from io import StringIO

from commands.admin_notifications import get_admin_ids
from storage import thanksgiving

logger = logging.getLogger(__name__)


async def thanksgiving_entries(update, context):
    chat, user = update.effective_chat, update.effective_user
    if not chat or chat.type != "private" or not user or user.id not in get_admin_ids():
        return

    try:
        entries = await asyncio.to_thread(thanksgiving.all_entries)
    except thanksgiving.ContestStorageError:
        logger.exception("Cannot export Thanksgiving contest submissions")
        await update.effective_message.reply_text("Список заявок временно недоступен. Попробуйте ещё раз.")
        return
    if not entries:
        await update.effective_message.reply_text("На конкурс «День благодарения» пока нет заявок.")
        return

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["telegram_id", "telegram_username", "url", "submitted_at", "rules_version"])
    writer.writeheader()
    writer.writerows(entries)
    await update.effective_message.reply_document(
        document=output.getvalue().encode("utf-8-sig"), filename="thanksgiving-2026.csv",
        caption=f"День благодарения · Заявок: {len(entries)}",
    )
