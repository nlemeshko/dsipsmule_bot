#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сохранение регистраций NASSAL2026 в S3-совместимое Object Storage.
"""

import csv
import io
import logging
import mimetypes
import os
from pathlib import Path
from datetime import datetime, UTC
from uuid import uuid4


logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = "https://nbg1.your-objectstorage.com"
S3_BUCKET_NAME = "nassal2026"
S3_REGISTRATIONS_KEY = "registrations/nassal2026_registrations.csv"
S3_AVATARS_PREFIX = "avatars"
CSV_HEADERS = [
    "registered_at_utc",
    "telegram_user_id",
    "telegram_username",
    "telegram_full_name",
    "participants",
    "category_code",
    "category_name",
    "avatar_url",
]


def _get_s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 не установлен. Установите зависимости из requirements.txt"
        ) from exc

    access_key = os.getenv("S3_ACCESS_KEY")
    secret_key = os.getenv("S3_SECRET_KEY")
    if not access_key or not secret_key:
        raise RuntimeError("S3_ACCESS_KEY и/или S3_SECRET_KEY не заданы")

    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )


def append_registration_row(registration: dict):
    """Добавляет строку в CSV-файл регистраций внутри бакета."""
    client = _get_s3_client()

    rows = []
    try:
        response = client.get_object(Bucket=S3_BUCKET_NAME, Key=S3_REGISTRATIONS_KEY)
        existing_csv = response["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(existing_csv))
        rows.extend(_normalize_registration_row(row) for row in reader)
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл регистраций ещё не существует, будет создан заново")
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл регистраций ещё не существует, будет создан заново")
        else:
            raise

    rows.append(registration)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerows(rows)

    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_REGISTRATIONS_KEY,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv; charset=utf-8",
    )


def load_registration_rows() -> list[dict]:
    """Возвращает все строки регистраций из CSV-файла в Object Storage."""
    client = _get_s3_client()

    try:
        response = client.get_object(Bucket=S3_BUCKET_NAME, Key=S3_REGISTRATIONS_KEY)
        existing_csv = response["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(existing_csv))
        return [_normalize_registration_row(row) for row in reader]
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл регистраций ещё не существует")
        return []
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл регистраций ещё не существует")
            return []
        raise


def find_registration_by_user_id(user_id: int) -> dict | None:
    """Ищет регистрацию пользователя по Telegram user_id."""
    user_id_str = str(user_id)
    for row in load_registration_rows():
        if row.get("telegram_user_id", "") == user_id_str:
            return row
    return None


def delete_registration_by_user_id(user_id: int) -> dict | None:
    """Удаляет регистрацию пользователя по Telegram user_id и возвращает удалённую строку."""
    client = _get_s3_client()
    user_id_str = str(user_id)
    rows = load_registration_rows()

    deleted_row = None
    remaining_rows = []
    for row in rows:
        if deleted_row is None and row.get("telegram_user_id", "") == user_id_str:
            deleted_row = row
            continue
        remaining_rows.append(row)

    if deleted_row is None:
        return None

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerows(remaining_rows)

    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=S3_REGISTRATIONS_KEY,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv; charset=utf-8",
    )
    return deleted_row


def build_registration_row(
    user_id: int,
    username: str | None,
    full_name: str | None,
    participants: str,
    category_code: str,
    category_name: str,
    avatar_url: str | None,
) -> dict:
    """Собирает строку регистрации в формате CSV."""
    return {
        "registered_at_utc": datetime.now(UTC).isoformat(),
        "telegram_user_id": str(user_id),
        "telegram_username": username or "",
        "telegram_full_name": full_name or "",
        "participants": participants,
        "category_code": category_code,
        "category_name": category_name,
        "avatar_url": avatar_url or "",
    }


def upload_avatar_bytes(
    avatar_bytes: bytes,
    telegram_file_path: str | None = None,
    content_type: str | None = None,
) -> str:
    """Загружает аватар в Object Storage и возвращает публичный URL."""
    client = _get_s3_client()

    extension = _resolve_avatar_extension(
        telegram_file_path=telegram_file_path,
        content_type=content_type,
    )
    object_key = (
        f"{S3_AVATARS_PREFIX}/"
        f"{datetime.now(UTC).strftime('%Y/%m/%d')}/"
        f"{uuid4().hex}{extension}"
    )

    guessed_content_type = content_type or mimetypes.guess_type(f"avatar{extension}")[0] or "application/octet-stream"
    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=object_key,
        Body=avatar_bytes,
        ContentType=guessed_content_type,
    )
    return _build_public_object_url(object_key)


def _normalize_registration_row(row: dict) -> dict:
    """Приводит старые и новые строки CSV к актуальной схеме."""
    normalized = {header: row.get(header, "") for header in CSV_HEADERS}
    if not normalized["avatar_url"]:
        normalized["avatar_url"] = row.get("avatar_file_id", "")
    return normalized


def _resolve_avatar_extension(
    telegram_file_path: str | None,
    content_type: str | None,
) -> str:
    """Определяет расширение файла аватара."""
    if telegram_file_path:
        suffix = Path(telegram_file_path).suffix.lower()
        if suffix:
            return suffix

    guessed_suffix = mimetypes.guess_extension(content_type or "")
    if guessed_suffix:
        return guessed_suffix

    return ".jpg"


def _build_public_object_url(object_key: str) -> str:
    """Собирает публичный URL для объекта внутри бакета."""
    public_base_url = os.getenv("S3_PUBLIC_BASE_URL")
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{object_key}"

    return f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET_NAME}/{object_key}"
