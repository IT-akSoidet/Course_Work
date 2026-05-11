from datetime import datetime

from app.core.config import MOSCOW_TZ

DATETIME_FORMATS: tuple[str, ...] = ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M")

STATUS_LABELS: dict[int, str] = {
    1: "На рассмотрении",
    2: "Подтверждена",
    3: "Отклонена",
    4: "Отменена",
}


def parse_datetime_input(raw_value: str) -> datetime:
    value = raw_value.strip()
    for dt_format in DATETIME_FORMATS:
        try:
            naive = datetime.strptime(value, dt_format)
            return naive.replace(tzinfo=MOSCOW_TZ)
        except ValueError:
            continue
    raise ValueError("Неверный формат даты и времени.")


def format_dt(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ)
    return dt.strftime("%d.%m.%Y %H:%M")


def format_time(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ)
    return dt.strftime("%H:%M")


def format_status(status_id: int) -> str:
    return STATUS_LABELS.get(status_id, f"Статус #{status_id}")
