from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import RoomUnavailability


@dataclass
class ScheduleSlot:
    room_id: int
    starts_at: datetime
    ends_at: datetime
    source_external_id: str | None = None
    comment: str | None = None


class ScheduleProvider(Protocol):
    def load_slots(self) -> list[ScheduleSlot]: ...


def _parse_dt(raw: str, primary: str = "%Y-%m-%d %H:%M") -> datetime:
    value = raw.strip()
    for fmt in (primary, "%d.%m.%Y %H:%M"):
        try:
            naive = datetime.strptime(value, fmt)
            return naive.replace(tzinfo=MOSCOW_TZ)
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {value}")


def _rows_to_slots(reader: csv.DictReader) -> list[ScheduleSlot]:
    required = {"room_id", "starts_at", "ends_at"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError("CSV должен содержать колонки: room_id, starts_at, ends_at.")
    slots: list[ScheduleSlot] = []
    for row in reader:
        slots.append(
            ScheduleSlot(
                room_id=int(row["room_id"].strip()),
                starts_at=_parse_dt(row["starts_at"]),
                ends_at=_parse_dt(row["ends_at"]),
                source_external_id=(row.get("external_id") or "").strip() or None,
                comment=(row.get("comment") or "").strip() or None,
            )
        )
    return slots


class CsvScheduleProvider:
    """Load schedule from a CSV file on disk or from raw bytes (Telegram upload)."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        content: bytes | None = None,
        dt_format: str = "%Y-%m-%d %H:%M",
    ) -> None:
        self.file_path = Path(file_path) if file_path else None
        self.content = content
        self.dt_format = dt_format

    def load_slots(self) -> list[ScheduleSlot]:
        if self.content is not None:
            text_content = self.content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text_content))
            return _rows_to_slots(reader)
        if self.file_path is not None:
            with self.file_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                return _rows_to_slots(reader)
        raise ValueError("Укажите file_path или content.")


class ScheduleImporter:
    def __init__(self, session: AsyncSession, provider: ScheduleProvider) -> None:
        self.session = session
        self.provider = provider

    async def import_schedule(self, source: str = "schedule_csv", replace_source: bool = True) -> int:
        slots = self.provider.load_slots()
        valid = [s for s in slots if s.starts_at < s.ends_at]

        seen: dict[tuple[int, datetime, datetime], ScheduleSlot] = {}
        for slot in valid:
            seen[(slot.room_id, slot.starts_at, slot.ends_at)] = slot
        final = list(seen.values())

        if self.session.in_transaction():
            await self._apply(final, source, replace_source)
            return len(final)

        async with self.session.begin():
            await self._apply(final, source, replace_source)
        return len(final)

    async def _apply(self, slots: list[ScheduleSlot], source: str, replace: bool) -> None:
        if replace:
            await self.session.execute(
                delete(RoomUnavailability).where(RoomUnavailability.source == source)
            )
        self.session.add_all(
            [
                RoomUnavailability(
                    room_id=s.room_id,
                    starts_at=s.starts_at,
                    ends_at=s.ends_at,
                    source=source,
                    source_external_id=s.source_external_id,
                    comment=s.comment,
                )
                for s in slots
            ]
        )
        await self.session.flush()
