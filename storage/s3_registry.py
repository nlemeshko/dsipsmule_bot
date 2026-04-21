#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сохранение регистраций NASSAL2026 в S3-совместимое Object Storage.
"""

import csv
import io
import logging
import os
from datetime import datetime, UTC


logger = logging.getLogger(__name__)

S3_ENDPOINT_URL = "https://nbg1.your-objectstorage.com"
S3_BUCKET_NAME = "nassal2026"
S3_REGISTRATIONS_KEY = "registrations/nassal2026_registrations.csv"
CSV_HEADERS = [
    "registered_at_utc",
    "telegram_user_id",
    "telegram_username",
    "telegram_full_name",
    "participants",
    "category_code",
    "category_name",
    "avatar_file_id",
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
        rows.extend(reader)
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
        return list(reader)
    except client.exceptions.NoSuchKey:
        logger.info("CSV-файл регистраций ещё не существует")
        return []
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404"}:
            logger.info("CSV-файл регистраций ещё не существует")
            return []
        raise


def build_registration_row(
    user_id: int,
    username: str | None,
    full_name: str | None,
    participants: str,
    category_code: str,
    category_name: str,
    avatar_file_id: str | None,
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
        "avatar_file_id": avatar_file_id or "",
    }
