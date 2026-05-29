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
import re
import time
from pathlib import Path
from datetime import datetime, UTC
from uuid import uuid4


logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = "https://nbg1.your-objectstorage.com"
S3_BUCKET_NAME = "nassal2026"
S3_REGISTRATIONS_KEY = "registrations/nassal2026_registrations.csv"
S3_FINAL_REGISTRATIONS_KEY = "registrations/nassal2026_final.csv"
S3_AVATARS_PREFIX = "avatars"
S3_FIRST_STAGE_PREFIX = "second_stage"
S3_FIRST_STAGE_FILES_PREFIX = "second_stage_files"
S3_FINAL_PREFIX = "final"
S3_FINAL_FILES_PREFIX = "final_files"
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
FIRST_STAGE_HEADERS = [
    "submitted_at_utc",
    "telegram_user_id",
    "telegram_username",
    "telegram_full_name",
    "participants",
    "category_code",
    "category_name",
    "work_type",
    "work_url",
    "work_file_id",
    "work_text",
]
S3_RETRYABLE_ERROR_CODES = {
    "SlowDown",
    "RequestTimeout",
    "InternalError",
    "InternalServerError",
    "ServiceUnavailable",
    "Throttling",
}
S3_MAX_ATTEMPTS = 10
S3_MANUAL_RETRY_ATTEMPTS = 4
S3_MANUAL_RETRY_BASE_DELAY_SECONDS = 1.0


def _get_s3_client():
    try:
        import boto3
        from botocore.config import Config
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
        config=Config(
            retries={"max_attempts": S3_MAX_ATTEMPTS, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


def _is_retryable_s3_exception(exc: Exception) -> bool:
    error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    if error_code in S3_RETRYABLE_ERROR_CODES:
        return True

    exc_name = exc.__class__.__name__
    return exc_name in {
        "ConnectionClosedError",
        "ConnectTimeoutError",
        "EndpointConnectionError",
        "HTTPClientError",
        "ReadTimeoutError",
        "ResponseStreamingError",
    }


def _run_s3_operation(operation, *, operation_name: str, storage_key: str | None = None):
    for attempt in range(1, S3_MANUAL_RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_s3_exception(exc) or attempt == S3_MANUAL_RETRY_ATTEMPTS:
                raise

            delay_seconds = S3_MANUAL_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Повторяем S3 %s для %s после ошибки %s (попытка %s/%s, ждём %.1fс)",
                operation_name,
                storage_key or "unknown key",
                exc,
                attempt,
                S3_MANUAL_RETRY_ATTEMPTS,
                delay_seconds,
            )
            time.sleep(delay_seconds)


def append_registration_row(registration: dict):
    """Добавляет строку в CSV-файл регистраций внутри бакета."""
    client = _get_s3_client()

    rows = []
    try:
        response = _run_s3_operation(
            lambda: client.get_object(Bucket=S3_BUCKET_NAME, Key=S3_REGISTRATIONS_KEY),
            operation_name="get_object",
            storage_key=S3_REGISTRATIONS_KEY,
        )
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

    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_REGISTRATIONS_KEY,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        ),
        operation_name="put_object",
        storage_key=S3_REGISTRATIONS_KEY,
    )


def load_registration_rows() -> list[dict]:
    """Возвращает все строки регистраций из CSV-файла в Object Storage."""
    client = _get_s3_client()

    try:
        response = _run_s3_operation(
            lambda: client.get_object(Bucket=S3_BUCKET_NAME, Key=S3_REGISTRATIONS_KEY),
            operation_name="get_object",
            storage_key=S3_REGISTRATIONS_KEY,
        )
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


def load_final_registration_rows() -> list[dict]:
    """Возвращает все строки финалистов из CSV-файла в Object Storage."""
    client = _get_s3_client()

    try:
        response = _run_s3_operation(
            lambda: client.get_object(Bucket=S3_BUCKET_NAME, Key=S3_FINAL_REGISTRATIONS_KEY),
            operation_name="get_object",
            storage_key=S3_FINAL_REGISTRATIONS_KEY,
        )
        existing_csv = response["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(existing_csv))
        return [_normalize_registration_row(row) for row in reader]
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл финалистов ещё не существует")
        return []
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл финалистов ещё не существует")
            return []
        raise


def find_registration_by_user_id(user_id: int) -> dict | None:
    """Ищет регистрацию пользователя по Telegram user_id."""
    user_id_str = str(user_id)
    for row in load_registration_rows():
        if row.get("telegram_user_id", "") == user_id_str:
            return row
    return None


def find_final_registration_by_user_id(user_id: int) -> dict | None:
    """Ищет финалиста по Telegram user_id."""
    user_id_str = str(user_id)
    for row in load_final_registration_rows():
        if row.get("telegram_user_id", "") == user_id_str:
            return row
    return None


def registration_exists(user_id: int, participants: str, category_code: str) -> bool:
    """Проверяет, что регистрация пользователя действительно присутствует в CSV."""
    user_id_str = str(user_id)
    normalized_participants = _normalize_participants(participants)
    normalized_category_code = category_code.strip()

    for row in load_registration_rows():
        if (
            row.get("telegram_user_id", "") == user_id_str
            and _normalize_participants(row.get("participants", "")) == normalized_participants
            and (row.get("category_code", "") or "").strip() == normalized_category_code
        ):
            return True
    return False


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

    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_REGISTRATIONS_KEY,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        ),
        operation_name="put_object",
        storage_key=S3_REGISTRATIONS_KEY,
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
        "participants": _normalize_participants(participants),
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
    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
            Body=avatar_bytes,
            ContentType=guessed_content_type,
        ),
        operation_name="put_object",
        storage_key=object_key,
    )
    return _build_public_object_url(object_key)


def upload_first_stage_file_bytes(
    file_bytes: bytes,
    work_type: str,
    telegram_file_path: str | None = None,
    content_type: str | None = None,
) -> str:
    """Загружает файл первого этапа в Object Storage и возвращает публичный URL."""
    client = _get_s3_client()

    extension = _resolve_media_extension(
        telegram_file_path=telegram_file_path,
        content_type=content_type,
        work_type=work_type,
    )
    object_key = (
        f"{S3_FIRST_STAGE_FILES_PREFIX}/"
        f"{datetime.now(UTC).strftime('%Y/%m/%d')}/"
        f"{uuid4().hex}{extension}"
    )

    guessed_content_type = (
        content_type
        or mimetypes.guess_type(f"work{extension}")[0]
        or "application/octet-stream"
    )
    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
            Body=file_bytes,
            ContentType=guessed_content_type,
        ),
        operation_name="put_object",
        storage_key=object_key,
    )
    return _build_public_object_url(object_key)


def upload_final_file_bytes(
    file_bytes: bytes,
    work_type: str,
    telegram_file_path: str | None = None,
    content_type: str | None = None,
) -> str:
    """Загружает файл финала в Object Storage и возвращает публичный URL."""
    client = _get_s3_client()

    extension = _resolve_media_extension(
        telegram_file_path=telegram_file_path,
        content_type=content_type,
        work_type=work_type,
    )
    object_key = (
        f"{S3_FINAL_FILES_PREFIX}/"
        f"{datetime.now(UTC).strftime('%Y/%m/%d')}/"
        f"{uuid4().hex}{extension}"
    )

    guessed_content_type = (
        content_type
        or mimetypes.guess_type(f"work{extension}")[0]
        or "application/octet-stream"
    )
    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
            Body=file_bytes,
            ContentType=guessed_content_type,
        ),
        operation_name="put_object",
        storage_key=object_key,
    )
    return _build_public_object_url(object_key)


def append_first_stage_submission_row(storage_key: str, submission: dict):
    """Добавляет строку в CSV-файл работ первого этапа."""
    client = _get_s3_client()

    rows = []
    try:
        response = _run_s3_operation(
            lambda: client.get_object(Bucket=S3_BUCKET_NAME, Key=storage_key),
            operation_name="get_object",
            storage_key=storage_key,
        )
        existing_csv = response["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(existing_csv))
        rows.extend(_normalize_first_stage_row(row) for row in reader)
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл первого этапа %s ещё не существует", storage_key)
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл первого этапа %s ещё не существует", storage_key)
        else:
            raise

    rows.append(submission)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIRST_STAGE_HEADERS)
    writer.writeheader()
    writer.writerows(rows)

    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=storage_key,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        ),
        operation_name="put_object",
        storage_key=storage_key,
    )


def load_first_stage_rows(storage_key: str) -> list[dict]:
    """Возвращает все строки работ первого этапа из указанного CSV."""
    client = _get_s3_client()

    try:
        response = _run_s3_operation(
            lambda: client.get_object(Bucket=S3_BUCKET_NAME, Key=storage_key),
            operation_name="get_object",
            storage_key=storage_key,
        )
        existing_csv = response["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(existing_csv))
        return [_normalize_first_stage_row(row) for row in reader]
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл первого этапа %s ещё не существует", storage_key)
        return []
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл первого этапа %s ещё не существует", storage_key)
            return []
        raise


def find_first_stage_submission_by_user_id(user_id: int) -> tuple[str, dict] | None:
    """Ищет работу пользователя во всех CSV первого этапа."""
    user_id_str = str(user_id)
    for storage_key in _get_all_first_stage_storage_keys():
        for row in load_first_stage_rows(storage_key):
            if row.get("telegram_user_id", "") == user_id_str:
                return storage_key, row
    return None


def delete_first_stage_submission_by_user_id(user_id: int) -> tuple[str, dict] | None:
    """Удаляет работу пользователя из CSV первого этапа и возвращает удалённую строку."""
    client = _get_s3_client()
    found_submission = find_first_stage_submission_by_user_id(user_id)
    if found_submission is None:
        return None

    storage_key, existing_row = found_submission
    rows = load_first_stage_rows(storage_key)
    user_id_str = str(user_id)

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
    writer = csv.DictWriter(output, fieldnames=FIRST_STAGE_HEADERS)
    writer.writeheader()
    writer.writerows(remaining_rows)

    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=storage_key,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        ),
        operation_name="put_object",
        storage_key=storage_key,
    )
    return storage_key, existing_row


def build_first_stage_submission_row(
    user_id: int,
    username: str | None,
    full_name: str | None,
    participants: str,
    category_code: str | None,
    category_name: str | None,
    work_type: str,
    work_url: str = "",
    work_file_id: str = "",
    work_text: str = "",
) -> dict:
    """Собирает строку для сохранения работы первого этапа."""
    normalized_category_code = (category_code or "").strip()
    normalized_category_name = (category_name or "").strip()
    return {
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "telegram_user_id": str(user_id),
        "telegram_username": username or "",
        "telegram_full_name": full_name or "",
        "participants": _normalize_participants(participants),
        "category_code": normalized_category_code,
        "category_name": normalized_category_name,
        "work_type": (work_type or "").strip(),
        "work_url": (work_url or "").strip(),
        "work_file_id": (work_file_id or "").strip(),
        "work_text": (work_text or "").strip(),
    }


def get_first_stage_storage_key(category_code: str | None) -> str:
    """Возвращает ключ CSV-файла для сохранения работы первого этапа."""
    normalized_category_code = (category_code or "").strip()
    if normalized_category_code in {"1", "2", "3", "4"}:
        return f"{S3_FIRST_STAGE_PREFIX}/{normalized_category_code}.csv"
    return f"{S3_FIRST_STAGE_PREFIX}/other.csv"


def get_final_storage_key(category_code: str | None) -> str:
    """Возвращает ключ CSV-файла для сохранения работы финала."""
    normalized_category_code = (category_code or "").strip()
    if normalized_category_code in {"1", "2", "3", "4"}:
        return f"{S3_FINAL_PREFIX}/{normalized_category_code}.csv"
    return f"{S3_FINAL_PREFIX}/other.csv"


def _get_all_first_stage_storage_keys() -> list[str]:
    """Возвращает список всех CSV первого этапа."""
    return [
        f"{S3_FIRST_STAGE_PREFIX}/1.csv",
        f"{S3_FIRST_STAGE_PREFIX}/2.csv",
        f"{S3_FIRST_STAGE_PREFIX}/3.csv",
        f"{S3_FIRST_STAGE_PREFIX}/4.csv",
        f"{S3_FIRST_STAGE_PREFIX}/other.csv",
    ]


def _get_all_final_storage_keys() -> list[str]:
    """Возвращает список всех CSV финала."""
    return [
        f"{S3_FINAL_PREFIX}/1.csv",
        f"{S3_FINAL_PREFIX}/2.csv",
        f"{S3_FINAL_PREFIX}/3.csv",
        f"{S3_FINAL_PREFIX}/4.csv",
        f"{S3_FINAL_PREFIX}/other.csv",
    ]


def find_final_submission_by_user_id(user_id: int) -> tuple[str, dict] | None:
    """Ищет работу пользователя во всех CSV финала."""
    user_id_str = str(user_id)
    for storage_key in _get_all_final_storage_keys():
        for row in load_first_stage_rows(storage_key):
            if row.get("telegram_user_id", "") == user_id_str:
                return storage_key, row
    return None


def delete_final_submission_by_user_id(user_id: int) -> tuple[str, dict] | None:
    """Удаляет работу пользователя из CSV финала и возвращает удалённую строку."""
    client = _get_s3_client()
    found_submission = find_final_submission_by_user_id(user_id)
    if found_submission is None:
        return None

    storage_key, existing_row = found_submission
    rows = load_first_stage_rows(storage_key)
    user_id_str = str(user_id)

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
    writer = csv.DictWriter(output, fieldnames=FIRST_STAGE_HEADERS)
    writer.writeheader()
    writer.writerows(remaining_rows)

    _run_s3_operation(
        lambda: client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=storage_key,
            Body=output.getvalue().encode("utf-8"),
            ContentType="text/csv; charset=utf-8",
        ),
        operation_name="put_object",
        storage_key=storage_key,
    )
    return storage_key, existing_row


def _normalize_registration_row(row: dict) -> dict:
    """Приводит старые и новые строки CSV к актуальной схеме."""
    normalized = {header: row.get(header, "") for header in CSV_HEADERS}
    normalized["participants"] = _normalize_participants(normalized["participants"])
    if not normalized["avatar_url"]:
        normalized["avatar_url"] = row.get("avatar_file_id", "")
    return normalized


def _normalize_first_stage_row(row: dict) -> dict:
    """Приводит строки первого этапа к актуальной схеме."""
    normalized = {header: row.get(header, "") for header in FIRST_STAGE_HEADERS}
    normalized["participants"] = _normalize_participants(normalized["participants"])
    if not normalized["work_type"]:
        normalized["work_type"] = "link" if normalized["work_url"] else "unknown"
    return normalized


def _normalize_participants(value: str | None) -> str:
    """Схлопывает переносы строк и повторяющиеся пробелы в имени участника."""
    return re.sub(r"\s+", " ", (value or "")).strip()


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


def _resolve_media_extension(
    telegram_file_path: str | None,
    content_type: str | None,
    work_type: str | None,
) -> str:
    """Определяет расширение медиафайла первого этапа."""
    if telegram_file_path:
        suffix = Path(telegram_file_path).suffix.lower()
        if suffix:
            return suffix

    guessed_suffix = mimetypes.guess_extension(content_type or "")
    if guessed_suffix:
        return guessed_suffix

    if work_type == "photo":
        return ".jpg"
    if work_type == "voice":
        return ".ogg"
    if work_type == "audio":
        return ".mp3"

    return ".bin"


def _build_public_object_url(object_key: str) -> str:
    """Собирает публичный URL для объекта внутри бакета."""
    public_base_url = os.getenv("S3_PUBLIC_BASE_URL")
    if public_base_url:
        return f"{public_base_url.rstrip('/')}/{object_key}"

    return f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET_NAME}/{object_key}"
