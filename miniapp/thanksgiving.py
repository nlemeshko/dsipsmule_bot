"""Telegram-authenticated endpoints for the contest."""

import asyncio
import logging
from datetime import UTC, datetime

from aiohttp import web

from storage import thanksgiving

logger = logging.getLogger(__name__)


def _response(links):
    return web.json_response({"open": datetime.now(UTC) < thanksgiving.CLOSES_AT, "links": links})


async def status(request):
    try:
        return _response(await asyncio.to_thread(thanksgiving.user_links, request["user"]["id"]))
    except thanksgiving.ContestStorageError:
        logger.exception("Cannot read Thanksgiving contest submissions")
        raise web.HTTPServiceUnavailable(reason="Список заявок временно недоступен. Попробуйте ещё раз.")


async def submit(request):
    received_at = datetime.now(UTC)
    body = await request.json()
    if not isinstance(body, dict) or body.get("accepted_rules") is not True:
        raise ValueError("Подтвердите, что прочитали правила конкурса.")
    url = thanksgiving.recording_url(body.get("url"))
    try:
        links = await asyncio.to_thread(thanksgiving.submit, request["user"], url, received_at)
    except (thanksgiving.ContestClosed, thanksgiving.DuplicateSubmission) as exc:
        raise web.HTTPConflict(reason=str(exc)) from exc
    except thanksgiving.ContestStorageError:
        logger.exception("Cannot save Thanksgiving contest submission")
        raise web.HTTPServiceUnavailable(reason="Не удалось подтвердить сохранение заявки. Попробуйте ещё раз.")
    return _response(links)
