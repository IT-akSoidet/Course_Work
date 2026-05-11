from datetime import datetime

import pytest

from app.bot.parsers import format_dt, format_status, parse_datetime_input
from app.core.config import MOSCOW_TZ


def test_parse_datetime_iso_format() -> None:
    assert parse_datetime_input("2026-05-01 12:30") == datetime(2026, 5, 1, 12, 30, tzinfo=MOSCOW_TZ)


def test_parse_datetime_ru_format() -> None:
    assert parse_datetime_input("01.05.2026 12:30") == datetime(2026, 5, 1, 12, 30, tzinfo=MOSCOW_TZ)


def test_parse_datetime_invalid() -> None:
    with pytest.raises(ValueError):
        parse_datetime_input("05/01/2026 12:30")


def test_format_dt() -> None:
    dt = datetime(2026, 5, 1, 12, 30, tzinfo=MOSCOW_TZ)
    assert format_dt(dt) == "01.05.2026 12:30"


def test_format_status_known() -> None:
    assert format_status(1) == "На рассмотрении"
    assert format_status(2) == "Подтверждена"


def test_format_status_unknown() -> None:
    assert "99" in format_status(99)
