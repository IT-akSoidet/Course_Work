import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from app.webapp.auth import validate_webapp_init_data


def _build_init_data(bot_token: str, user_payload: dict, auth_date: int | None = None) -> str:
    auth_date = auth_date or int(time.time())
    payload = {
        "auth_date": str(auth_date),
        "query_id": "AAEAAAE",
        "user": json.dumps(user_payload, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={payload[key]}" for key in sorted(payload))
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    payload["hash"] = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return urlencode(payload)


def test_validate_webapp_init_data_success(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "test-token-123"
    monkeypatch.setenv("BOT_TOKEN", bot_token)

    init_data = _build_init_data(
        bot_token=bot_token,
        user_payload={"id": 123456789, "first_name": "Иван", "last_name": "Петров", "username": "ivan"},
    )
    user = validate_webapp_init_data(init_data)

    assert user.telegram_id == 123456789
    assert user.full_name == "Иван Петров"
    assert user.username == "ivan"


def test_validate_webapp_init_data_invalid_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    bot_token = "test-token-123"
    monkeypatch.setenv("BOT_TOKEN", bot_token)

    init_data = _build_init_data(
        bot_token=bot_token,
        user_payload={"id": 111, "first_name": "A"},
    )
    broken = init_data.replace("hash=", "hash=broken")

    with pytest.raises(HTTPException) as exc:
        validate_webapp_init_data(broken)
    assert exc.value.status_code == 401
