import re
from datetime import date, datetime, time

from app.core.config import MOSCOW_TZ

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_INTERVAL_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})$")

RU_MONTHS_GEN = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

RU_WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def parse_time(raw: str) -> time:
    raw = (raw or "").strip().replace(".", ":")
    m = _TIME_RE.match(raw)
    if not m:
        raise ValueError("Неверный формат времени. Ожидается ЧЧ:ММ.")
    hours, minutes = int(m.group(1)), int(m.group(2))
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError("Время должно быть в диапазоне 00:00–23:59.")
    return time(hour=hours, minute=minutes)


def parse_interval(raw: str) -> tuple[time, time]:
    raw = (raw or "").strip().replace(".", ":")
    m = _INTERVAL_RE.match(raw)
    if not m:
        raise ValueError("Неверный формат. Ожидается ЧЧ:ММ-ЧЧ:ММ.")
    h1, mi1, h2, mi2 = map(int, m.groups())
    if not (0 <= h1 < 24 and 0 <= mi1 < 60 and 0 <= h2 < 24 and 0 <= mi2 < 60):
        raise ValueError("Время должно быть в диапазоне 00:00–23:59.")
    start = time(hour=h1, minute=mi1)
    end = time(hour=h2, minute=mi2)
    if end <= start:
        raise ValueError("Время окончания должно быть позже начала.")
    return start, end


def combine_date_time(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=MOSCOW_TZ)


def format_date_human(d: date) -> str:
    return f"{d.day} {RU_MONTHS_GEN[d.month]} {d.year}"


def format_date_short(d: date) -> str:
    return f"{d.day} {RU_MONTHS_GEN[d.month]}"


def format_date_btn(d: date, today: date) -> str:
    if d == today:
        return f"Сегодня, {d.day} {RU_MONTHS_GEN[d.month]}"
    if (d - today).days == 1:
        return f"Завтра, {d.day} {RU_MONTHS_GEN[d.month]}"
    return f"{RU_WEEKDAYS_SHORT[d.weekday()]}, {d.day} {RU_MONTHS_GEN[d.month]}"


def format_dt(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_time(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ)
    return dt.strftime("%H:%M")
