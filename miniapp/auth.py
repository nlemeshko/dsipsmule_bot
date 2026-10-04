"""Verify Telegram's signed initData before trusting any identity."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlsplit


def miniapp_url(value: str) -> str:
    value = value.strip()
    if value:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("MINI_APP_URL должен быть публичным HTTPS URL без логина и фрагмента")
    return value


def validate_init_data(raw: str, token: str, max_age: int = 3600, now: float | None = None) -> dict:
    if not raw or len(raw) > 16384:
        raise ValueError("Откройте приложение через Telegram")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Повторяющиеся поля авторизации")
    signature = fields.pop("hash", "")
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Не удалось подтвердить авторизацию Telegram")
    current = time.time() if now is None else now
    age = current - int(fields.get("auth_date", "0"))
    if age < -30 or age > max_age:
        raise ValueError("Сессия истекла. Закройте и снова откройте приложение")
    user = json.loads(fields.get("user", "null"))
    if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
        raise ValueError("Нет пользователя Telegram")
    if not isinstance(user.get("first_name"), str):
        raise ValueError("Некорректный пользователь Telegram")
    return user
