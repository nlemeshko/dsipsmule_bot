"""Website requests authenticated by the site backend."""
import asyncio
import base64
import binascii
import hmac
import json
import os
import time

from aiohttp import web

COMMANDS = {"ask", "draw", "chat", "ded", "guess", "mood", "prediction", "casino", "cat", "hall", "vote"}
CALLBACKS = {"button1", "button2", "button3"}

def website_user(request):
    secret = os.getenv("ACTIVITIES_SECRET", "")
    supplied = request.headers.get("X-Activities-Secret", "")
    if not secret or not hmac.compare_digest(secret.encode(), supplied.encode()):
        raise web.HTTPUnauthorized()
    if request.path == "/site-api/community":
        return None
    try:
        encoded = request.headers.get("X-Activities-User", "")
        data = json.loads(base64.b64decode(encoded, validate=True))
        user_id = data["id"]
        name = data["name"]
        if type(user_id) is not int or not 0 < user_id < 2**40 or not isinstance(name, str) or not name.strip():
            raise ValueError()
        return {"id": 2**51 + user_id, "first_name": name[:64], "username": f"site_{user_id}", "website": True}
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise web.HTTPUnauthorized() from None

def community_snapshot():
    from services import titles
    from storage.hall import load_hall_data

    state = titles.load_state()
    polls = [
        {"token": poll["token"], "name": poll["name"], "until": poll["until"], "counts": titles.counts(poll)}
        for poll in state["community"].get("title_polls", {}).values()
        if poll["message_id"] and not poll["closed"] and poll["until"] > time.time()
    ]
    results = [person["verdict"] for person in state["people"].values() if "verdict" in person]
    return {"hall": [{k: row[k] for k in ("category", "name", "date", "votes")} for row in load_hall_data()],
            "polls": sorted(polls, key=lambda row: row["until"]), "results": results, "choices": titles.CHOICES}

async def community(request):
    return web.json_response(await asyncio.to_thread(community_snapshot))

async def vote(request):
    from services import titles
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("choice"), str) or body["choice"] not in titles.CHOICES:
        raise ValueError("Выбери вариант голосования")
    token = request.match_info["token"]
    def cast():
        poll = titles.load_state()["community"].get("title_polls", {}).get(token)
        if not poll or not poll["message_id"]:
            raise ValueError("Голосование недоступно")
        return titles.vote(token, poll["chat_id"], request["user"]["id"], body["choice"])
    poll = await asyncio.to_thread(cast)
    return web.json_response({"counts": titles.counts(poll)})
