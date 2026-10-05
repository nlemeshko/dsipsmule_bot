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
    ded = state["community"].get("ded")
    if ded is not None and (not isinstance(ded, dict) or type(ded.get("count")) is not int or ded["count"] < 0
                           or not isinstance(ded.get("seen"), list) or len(ded["seen"]) > 256
                           or not all(isinstance(key, str) for key in ded["seen"])):
        raise ValueError("Invalid ded meter")
    mood = state["community"].get("mood")
    if mood is not None and (not isinstance(mood, dict) or not isinstance(mood.get("token"), str)
                            or not valid_time(mood.get("until")) or not isinstance(mood.get("votes"), dict)
                            or mood.get("mode") not in {"angry", "tired", "lyutik"}
                            or any(mode not in {"angry", "tired", "lyutik"} for mode in mood["votes"].values())):
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
