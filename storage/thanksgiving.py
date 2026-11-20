"""Authoritative Thanksgiving 2026 submissions in the bot's S3 bucket."""

import json
import re
from datetime import UTC, datetime
from threading import Lock
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError

from storage.hall import s3_storage

# Midnight at the end of November 27 in Europe/Kyiv.
CLOSES_AT = datetime(2026, 11, 27, 22, tzinfo=UTC)
KEY = "dsipsmule-bot/contests/thanksgiving-2026/submissions.json"
MAX_BYTES = 4 * 1024 * 1024
LOCK = Lock()


class ContestStorageError(RuntimeError):
    pass


class SubmissionConflict(ValueError):
    pass


class ContestClosed(ValueError):
    pass


def recording_url(value):
    error = "Пришлите прямую ссылку на запись в Smule."
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(error)
    value = value.strip()
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError(error)
    try:
        url = urlsplit(value)
    except ValueError as exc:
        raise ValueError(error) from exc
    match = re.fullmatch(r"/(?:sing-recording/|recording/[^/]+/)([0-9]+_[0-9]+)/?", url.path)
    if url.scheme != "https" or url.netloc.lower() not in {"smule.com", "www.smule.com"} or not match:
        raise ValueError(error)
    return f"https://www.smule.com/sing-recording/{match[1]}"


def _storage():
    try:
        configured = s3_storage()
    except (BotoCoreError, ValueError) as exc:
        raise ContestStorageError("Invalid S3 configuration") from exc
    if not configured:
        raise ContestStorageError("S3 is required for contest submissions")
    client, bucket, _ = configured
    return client, bucket


def _read(client, bucket):
    try:
        response = client.get_object(Bucket=bucket, Key=KEY)
        with response["Body"] as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ContestStorageError("Contest submissions exceed the storage limit")
        entries = json.loads(content)
        if not isinstance(entries, dict):
            raise ContestStorageError("Invalid contest submissions")
        return entries
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "NotFound"}:
            return {}
        raise ContestStorageError("Cannot read contest submissions") from exc
    except (BotoCoreError, ValueError) as exc:
        raise ContestStorageError("Cannot read contest submissions") from exc


def _own_links(entries, user_id):
    return [url for url, entry in entries.items() if entry["telegram_id"] == user_id]


def _save(client, bucket, entries):
    content = json.dumps(entries, ensure_ascii=False).encode("utf-8")
    if len(content) > MAX_BYTES:
        raise ContestStorageError("Contest submissions exceed the storage limit")
    try:
        client.put_object(Bucket=bucket, Key=KEY, Body=content, ContentType="application/json")
    except (BotoCoreError, ClientError) as exc:
        raise ContestStorageError("Cannot write contest submissions") from exc


def user_links(user_id):
    return _own_links(_read(*_storage()), user_id)


def all_entries():
    return list(_read(*_storage()).values())


def submit(user, url, received_at):
    # Helm deploys one bot process with Recreate. Serialize its writers so that
    # concurrent submissions cannot overwrite entries read by another request.
    with LOCK:
        client, bucket = _storage()
        entries = _read(client, bucket)
        own_links = _own_links(entries, user["id"])
        if url in own_links:
            return own_links
        if received_at >= CLOSES_AT:
            raise ContestClosed("Приём работ завершён.")
        if own_links:
            raise SubmissionConflict("Можно подать только одну работу. Чтобы заменить её, удалите текущую заявку.")
        if url in entries:
            raise SubmissionConflict("Эту запись уже подали на конкурс. Для дуэта достаточно одной заявки.")

        username = user.get("username", "")
        entries[url] = {
            "telegram_id": user["id"],
            "telegram_username": username if isinstance(username, str) and re.fullmatch(r"[A-Za-z0-9_]+", username) else "",
            "url": url,
            "submitted_at": received_at.isoformat(timespec="seconds"),
            "rules_version": 1,
        }
        _save(client, bucket, entries)
        return [url]


def remove(user_id, url):
    with LOCK:
        client, bucket = _storage()
        entries = _read(client, bucket)
        entry = entries.get(url)
        if entry and entry["telegram_id"] == user_id:
            del entries[url]
            _save(client, bucket, entries)
        return _own_links(entries, user_id)
