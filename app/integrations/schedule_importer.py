from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import Building, Room, ScheduleSlot

REQUIRED_COLUMNS = {
    "date",
    "start_time",
    "end_time",
    "subject",
    "teacher",
    "classroom",
    "building",
}


@dataclass
class ImportReport:
    processed_rows: int = 0
    inserted_slots: int = 0
    skipped_online: int = 0
    created_buildings: int = 0
    created_rooms: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class _ParsedRow:
    date: date
    starts_at: datetime
    ends_at: datetime
    subject: str
    teacher: str | None
    building_code: str
    classroom: str


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {value!r}")


def _parse_time(value: str) -> time:
    value = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат времени: {value!r}")


def _building_name(code: str) -> str:
    code = code.strip()
    return f"Корпус {code}"


def _parse_row(raw: dict[str, str]) -> _ParsedRow:
    d = _parse_date(raw["date"])
    t_start = _parse_time(raw["start_time"])
    t_end = _parse_time(raw["end_time"])

    starts_at = datetime.combine(d, t_start, tzinfo=MOSCOW_TZ)
    ends_at = datetime.combine(d, t_end, tzinfo=MOSCOW_TZ)
    if starts_at >= ends_at:
        raise ValueError("Время окончания должно быть позже начала.")

    return _ParsedRow(
        date=d,
        starts_at=starts_at,
        ends_at=ends_at,
        subject=(raw.get("subject") or "").strip() or "Занятие",
        teacher=(raw.get("teacher") or "").strip() or None,
        building_code=(raw.get("building") or "").strip(),
        classroom=(raw.get("classroom") or "").strip(),
    )


class CsvScheduleProvider:
    """Load CSV rows from disk path or raw bytes (Telegram document)."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        content: bytes | None = None,
    ) -> None:
        self.file_path = Path(file_path) if file_path else None
        self.content = content

    def read_rows(self) -> list[dict[str, str]]:
        if self.content is not None:
            text_content = self.content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text_content))
            return self._collect(reader)
        if self.file_path is not None:
            with self.file_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                return self._collect(reader)
        raise ValueError("Не указан источник данных (file_path или content).")

    @staticmethod
    def _collect(reader: csv.DictReader) -> list[dict[str, str]]:
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(
                "В CSV не хватает колонок: " + ", ".join(sorted(missing))
            )
        return list(reader)


class ScheduleImporter:
    def __init__(self, session: AsyncSession, provider: CsvScheduleProvider) -> None:
        self.session = session
        self.provider = provider

    async def import_schedule(self) -> ImportReport:
        rows = self.provider.read_rows()
        report = ImportReport(processed_rows=len(rows))

        parsed: list[_ParsedRow] = []
        for idx, row in enumerate(rows, start=2):
            building = (row.get("building") or "").strip().lower()
            classroom = (row.get("classroom") or "").strip().lower()
            if building == "online" or classroom == "online":
                report.skipped_online += 1
                continue
            try:
                parsed.append(_parse_row(row))
            except (KeyError, ValueError) as exc:
                report.errors.append(f"Строка {idx}: {exc}")

        async with self.session.begin():
            building_cache = await self._load_buildings()
            room_cache = await self._load_rooms()
            dates_in_file = {p.date for p in parsed}

            for p in parsed:
                building_name = _building_name(p.building_code)
                building_obj = building_cache.get(building_name)
                if building_obj is None:
                    building_obj = Building(name=building_name, address="")
                    self.session.add(building_obj)
                    await self.session.flush()
                    building_cache[building_name] = building_obj
                    report.created_buildings += 1

                room_key = (building_obj.id, p.classroom)
                room_obj = room_cache.get(room_key)
                if room_obj is None:
                    room_obj = Room(
                        building_id=building_obj.id,
                        name=p.classroom,
                        capacity=30,
                        is_active=True,
                    )
                    self.session.add(room_obj)
                    await self.session.flush()
                    room_cache[room_key] = room_obj
                    report.created_rooms += 1

                p._room_id = room_obj.id  # type: ignore[attr-defined]

            if dates_in_file:
                await self.session.execute(
                    delete(ScheduleSlot).where(ScheduleSlot.date.in_(dates_in_file))
                )

            for p in parsed:
                room_id = getattr(p, "_room_id", None)
                if room_id is None:
                    continue
                self.session.add(
                    ScheduleSlot(
                        room_id=room_id,
                        date=p.date,
                        starts_at=p.starts_at,
                        ends_at=p.ends_at,
                        subject=p.subject,
                        teacher=p.teacher,
                    )
                )
                report.inserted_slots += 1

        return report

    async def _load_buildings(self) -> dict[str, Building]:
        result = await self.session.execute(select(Building))
        return {b.name: b for b in result.scalars().all()}

    async def _load_rooms(self) -> dict[tuple[int, str], Room]:
        result = await self.session.execute(select(Room))
        return {(r.building_id, r.name): r for r in result.scalars().all()}
