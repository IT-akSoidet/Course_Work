from datetime import datetime

import pytest

from app.bot.parsers import parse_datetime_input
from app.core.config import MOSCOW_TZ


def test_parse_datetime_iso() -> None:
    result = parse_datetime_input("2026-05-01 12:00")
    assert result == datetime(2026, 5, 1, 12, 0, tzinfo=MOSCOW_TZ)


def test_parse_datetime_ru() -> None:
    result = parse_datetime_input("01.05.2026 12:00")
    assert result == datetime(2026, 5, 1, 12, 0, tzinfo=MOSCOW_TZ)


@pytest.mark.parametrize("bad_input", ["not-a-date", "2026/05/01 12:00", ""])
def test_parse_datetime_invalid(bad_input: str) -> None:
    with pytest.raises(ValueError):
        parse_datetime_input(bad_input)
