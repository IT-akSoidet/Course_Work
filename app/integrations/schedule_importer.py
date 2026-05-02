from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RoomUnavailability


@dataclass
class ScheduleSlot:
    room_id: int
    starts_at: datetime
    ends_at: datetime
    source_external_id: str | None = None
    comment: str | None = None


class ScheduleProvider(Protocol):
    def load_slots(self) -> list[ScheduleSlot]:
        """Returns schedule slots for import."""


class CsvScheduleProvider:
    """CSV columns: room_id,starts_at,ends_at,external_id,comment.

    Example datetime format: 2026-05-12 10:30
    """

    def __init__(self, file_path: str | Path, dt_format: str = "%Y-%m-%d %H:%M") -> None:
        self.file_path = Path(file_path)
        self.dt_format = dt_format

    def load_slots(self) -> list[ScheduleSlot]:
        slots: list[ScheduleSlot] = []
        with self.file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            required = {"room_id", "starts_at", "ends_at"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError("CSV должен содержать колонки room_id, starts_at, ends_at.")
            for row in reader:
                starts_at = datetime.strptime(row["starts_at"].strip(), self.dt_format)
                ends_at = datetime.strptime(row["ends_at"].strip(), self.dt_format)
                slots.append(
                    ScheduleSlot(
                        room_id=int(row["room_id"].strip()),
                        starts_at=starts_at,
                        ends_at=ends_at,
                        source_external_id=(row.get("external_id") or "").strip() or None,
                        comment=(row.get("comment") or "").strip() or None,
                    )
                )
        return slots


class ApiScheduleProvider:
    """Заглушка расширения под внешний API расписания."""

    def load_slots(self) -> list[ScheduleSlot]:
        return []


class ScheduleImporter:
    def __init__(self, session: AsyncSession, provider: ScheduleProvider) -> None:
        self.session = session
        self.provider = provider

    async def import_schedule(self, source: str = "schedule_csv", replace_source: bool = True) -> int:
        slots = self.provider.load_slots()

        async with self.session.begin():
            if replace_source:
                await self.session.execute(
                    delete(RoomUnavailability).where(RoomUnavailability.source == source)
                )
            for slot in slots:
                if slot.starts_at >= slot.ends_at:
                    continue
                self.session.add(
                    RoomUnavailability(
                        room_id=slot.room_id,
                        starts_at=slot.starts_at,
                        ends_at=slot.ends_at,
                        source=source,
                        source_external_id=slot.source_external_id,
                        comment=slot.comment,
                    )
                )
            await self.session.flush()
        return len(slots)
