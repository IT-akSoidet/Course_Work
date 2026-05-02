from datetime import datetime

import pytest

from app.bot.handlers.booking import _parse_booking_payload, _parse_rooms_payload


def test_parse_booking_payload_success() -> None:
    room_id, starts_at, ends_at, purpose = _parse_booking_payload(
        "/book 10101;2026-05-01 12:00;2026-05-01 14:00;Консультация"
    )
    assert room_id == 10101
    assert starts_at == datetime(2026, 5, 1, 12, 0)
    assert ends_at == datetime(2026, 5, 1, 14, 0)
    assert purpose == "Консультация"


def test_parse_rooms_payload_success() -> None:
    starts_at, ends_at, min_capacity = _parse_rooms_payload("/rooms 2026-05-01 12:00;2026-05-01 14:00;20")
    assert starts_at == datetime(2026, 5, 1, 12, 0)
    assert ends_at == datetime(2026, 5, 1, 14, 0)
    assert min_capacity == 20


@pytest.mark.parametrize(
    "payload",
    [
        "/book 10101;2026-05-01 12:00;2026-05-01 14:00",
        "/book no_int;2026-05-01 12:00;2026-05-01 14:00;Пара",
    ],
)
def test_parse_booking_payload_invalid(payload: str) -> None:
    with pytest.raises(ValueError):
        _parse_booking_payload(payload)
