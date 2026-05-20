from datetime import date

import pytest

from app.bot.parsers import (
    format_date_btn,
    format_date_human,
    parse_interval,
    parse_time,
)


def test_parse_time_valid() -> None:
    t = parse_time("10:00")
    assert t.hour == 10 and t.minute == 0


def test_parse_time_with_dot() -> None:
    t = parse_time("9.30")
    assert t.hour == 9 and t.minute == 30


@pytest.mark.parametrize("bad", ["", "10", "10:", "25:00", "12:60", "abc"])
def test_parse_time_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_time(bad)


def test_parse_interval_valid() -> None:
    start, end = parse_interval("10:00-14:00")
    assert start.hour == 10 and end.hour == 14


def test_parse_interval_dash_variants() -> None:
    start, end = parse_interval("10:00 – 14:00")
    assert start.hour == 10 and end.hour == 14


def test_parse_interval_end_before_start() -> None:
    with pytest.raises(ValueError):
        parse_interval("14:00-10:00")


def test_parse_interval_invalid_format() -> None:
    with pytest.raises(ValueError):
        parse_interval("10-14")


def test_format_date_human() -> None:
    assert format_date_human(date(2026, 5, 21)) == "21 мая 2026"


def test_format_date_btn_today() -> None:
    today = date(2026, 5, 21)
    assert format_date_btn(today, today) == "Сегодня, 21 мая"


def test_format_date_btn_tomorrow() -> None:
    today = date(2026, 5, 21)
    assert format_date_btn(date(2026, 5, 22), today) == "Завтра, 22 мая"


def test_format_date_btn_weekday() -> None:
    today = date(2026, 5, 21)
    label = format_date_btn(date(2026, 5, 23), today)
    assert "мая" in label and label.startswith("Сб")
