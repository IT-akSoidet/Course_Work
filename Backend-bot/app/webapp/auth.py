import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.core.config import get_settings

_AUTH_MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass(slots=True)
class WebAppUser:
    telegram_id: int
    full_name: str
    username: str | None


def _compute_telegram_hash(init_data: str, bot_token: str) -> str:
    pairs = parse_qsl(init_data, keep_blank_values=True)
    values = dict(pairs)
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Отсутствует подпись Telegram.")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values.keys()))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Некорректная подпись Telegram.")
    return received_hash


def _extract_user_from_init_data(init_data: str) -> WebAppUser:
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    auth_date_raw = values.get("auth_date")
    if auth_date_raw is None or not auth_date_raw.isdigit():
        raise HTTPException(status_code=401, detail="Некорректный auth_date.")
    auth_date = int(auth_date_raw)
    if int(time.time()) - auth_date > _AUTH_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Сессия WebApp устарела.")

    user_raw = values.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Не удалось определить пользователя Telegram.")
    try:
        user_payload = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Поврежден профиль Telegram.") from exc

    telegram_id = user_payload.get("id")
    if not isinstance(telegram_id, int):
        raise HTTPException(status_code=401, detail="Некорректный Telegram ID.")

    first_name = str(user_payload.get("first_name") or "").strip()
    last_name = str(user_payload.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part) or f"user_{telegram_id}"
    username = user_payload.get("username")
    username = str(username) if username else None
    return WebAppUser(telegram_id=telegram_id, full_name=full_name, username=username)


def validate_webapp_init_data(init_data: str) -> WebAppUser:
    settings = get_settings()
    if not settings.bot_token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN не настроен.")
    _compute_telegram_hash(init_data=init_data, bot_token=settings.bot_token)
    return _extract_user_from_init_data(init_data)


def _build_fallback_user(telegram_id: int, full_name: str | None = None) -> WebAppUser:
    safe_name = (full_name or "").strip() or f"user_{telegram_id}"
    return WebAppUser(telegram_id=telegram_id, full_name=safe_name, username=None)


async def get_webapp_user(
    x_telegram_init_data: str = Header(default=""),
    x_telegram_fallback_id: str = Header(default=""),
    x_telegram_fallback_name: str = Header(default=""),
) -> WebAppUser:
    init_data = x_telegram_init_data.strip()
    if init_data:
        return validate_webapp_init_data(init_data)

    settings = get_settings()
    if settings.app_env.lower() not in {"dev", "local", "test"}:
        raise HTTPException(status_code=401, detail="Отсутствует заголовок X-Telegram-Init-Data.")

    fallback_id = x_telegram_fallback_id.strip()
    if not fallback_id.isdigit():
        raise HTTPException(status_code=401, detail="Нет данных Telegram для dev-fallback авторизации.")
    return _build_fallback_user(telegram_id=int(fallback_id), full_name=x_telegram_fallback_name)
