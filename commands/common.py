#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Общие вспомогательные функции для команд бота.
"""

from functools import lru_cache
from io import BytesIO
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=128)
def read_binary_asset(relative_path: str) -> bytes | None:
    """Кэшированно читает бинарный ассет из проекта."""
    asset_path = BASE_DIR / relative_path
    try:
        return asset_path.read_bytes()
    except FileNotFoundError:
        return None


def build_binary_stream(relative_path: str, filename: str | None = None) -> BytesIO | None:
    """Создает новый поток из закэшированных байтов ассета."""
    asset_bytes = read_binary_asset(relative_path)
    if asset_bytes is None:
        return None

    stream = BytesIO(asset_bytes)
    stream.name = filename or Path(relative_path).name
    stream.seek(0)
    return stream
