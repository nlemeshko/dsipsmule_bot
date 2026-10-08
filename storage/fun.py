"""Durable community games and permanent cards; S3 is authoritative when configured."""

import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path
from threading import RLock

from botocore.exceptions import ClientError
from storage.hall import BASE, s3_storage
from services.fun_catalog import MOODS

LOCK = RLock()
MAX_STATE = 4 * 1024 * 1024
logger = logging.getLogger(__name__)


def state_path():
    return Path(os.getenv("DATA_DIR", str(BASE / "data"))) / "fun.json"


def empty_state():
    return {"version": 1, "people": {}, "community": {}, "games": {}}


def decode(content):
    if len(content) > MAX_STATE:
        raise ValueError("Community state is too large")
    state = json.loads(content)
    if (not isinstance(state, dict) or state.get("version") != 1
            or set(state) != {"version", "people", "community", "games"}
            or any(not isinstance(state[key], dict) for key in ("people", "community", "games"))):
        raise ValueError("Invalid community state")
    for person in state["people"].values():
        if not isinstance(person, dict):
            raise ValueError("Invalid permanent card")
        for kind in ("passport", "order"):
            card = person.get(kind)
            if card is not None and (not isinstance(card, dict) or not all(
                    isinstance(card.get(field), str) and card[field]
                    for field in ("number", "name", "title", "issued", "detail"))):
                raise ValueError("Invalid permanent card")
        verdict = person.get("verdict")
        if verdict is not None and (not isinstance(verdict, dict) or verdict.get("choice") not in {"legend", "bore"}
                                    or not isinstance(verdict.get("name"), str) or not valid_time(verdict.get("until"))
                                    or not valid_counts(verdict.get("counts"))):
            raise ValueError("Invalid title verdict")
    polls = state["community"].get("title_polls", {})
    if not isinstance(polls, dict):
        raise ValueError("Invalid title polls")
    for token, poll in polls.items():
        if (not isinstance(poll, dict) or poll.get("token") != token or not re.fullmatch(r"[0-9a-f]{12}", token)
                or type(poll.get("chat_id")) is not int or poll["chat_id"] >= 0
                or type(poll.get("source_id")) is not int or poll["source_id"] <= 0
                or type(poll.get("message_id")) is not int or poll["message_id"] < 0
                or not isinstance(poll.get("target"), str) or not re.fullmatch(r"-?[0-9]+", poll["target"])
                or not isinstance(poll.get("name"), str) or not poll["name"] or len(poll["name"]) > 80
                or not valid_time(poll.get("until")) or not isinstance(poll.get("votes"), dict)
                or any(choice not in {"legend", "bore"} for choice in poll["votes"].values())
                or type(poll.get("closed")) is not bool or type(poll.get("reported")) is not bool
                or (poll["closed"] and poll.get("result") not in {"legend", "bore", "tie", "empty"})):
            raise ValueError("Invalid title poll")
    ded = state["community"].get("ded")
    if ded is not None and (not isinstance(ded, dict) or type(ded.get("count")) is not int or ded["count"] < 0
                           or not isinstance(ded.get("seen"), list) or len(ded["seen"]) > 256
                           or not all(isinstance(key, str) for key in ded["seen"])):
        raise ValueError("Invalid ded meter")
    mood = state["community"].get("mood")
    if mood is not None and (not isinstance(mood, dict) or not isinstance(mood.get("token"), str)
                            or not valid_time(mood.get("until")) or not isinstance(mood.get("votes"), dict)
                            or mood.get("mode") not in MOODS
                            or any(mode not in MOODS for mode in mood["votes"].values())):
        raise ValueError("Invalid mood vote")
    for chat_id, game in state["games"].items():
        if (not re.fullmatch(r"-?[0-9]+", chat_id) or not isinstance(game, dict)
                or not valid_time(game.get("until")) or type(game.get("finished")) is not bool
                or not all(isinstance(game.get(field), str) and game[field]
                           for field in ("token", "emoji", "answer", "hint"))):
            raise ValueError("Invalid guessing game")
    return state


def valid_time(value):
    return type(value) in {int, float} and math.isfinite(value) and value > 0


def valid_counts(value):
    return (isinstance(value, dict) and set(value) == {"legend", "bore"}
            and all(type(count) is int and count >= 0 for count in value.values()))


def remote_storage():
    storage = s3_storage()
    if not storage:
        return None
    client, bucket, _ = storage
    key = os.getenv("FUN_S3_KEY", "dsipsmule-bot/fun/state.json").strip()
    if not key:
        raise ValueError("FUN_S3_KEY must not be empty")
    return client, bucket, key


def local_state():
    try:
        return decode(state_path().read_bytes())
    except FileNotFoundError:
        return empty_state()


def remote_state(storage):
    client, bucket, key = storage
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound"}:
            return None
        raise
    with response["Body"] as stream:
        return decode(stream.read(MAX_STATE + 1))


def cache(content):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def load_state():
    with LOCK:
        storage = remote_storage()
        if storage:
            state = remote_state(storage)
            if state is not None:
                return state
        return local_state()


def save_state(state):
    with LOCK:
        content = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        decode(content)
        storage = remote_storage()
        if storage:
            client, bucket, key = storage
            client.put_object(Bucket=bucket, Key=key, Body=content, ContentType="application/json; charset=utf-8")
            try:
                cache(content)
            except OSError:
                logger.warning("Community state saved in S3; local cache could not be updated")
        else:
            cache(content)


def update_state(change):
    with LOCK:
        state = load_state()
        changed, result = change(state)
        if changed:
            save_state(state)
        return result


def initialize_storage():
    with LOCK:
        storage = remote_storage()
        if storage and remote_state(storage) is None:
            save_state(local_state())
        return load_state()
