"""Импорт расписания ВШЭ из CSV файла.

Формат CSV:
  date,start_time,end_time,subject,subject_type,teacher,group,classroom,building
  2025-04-06,08:00,09:20,Программирование C/C++,практическое занятие,Климов А.,25КНТ-1,216,БП

Логика:
  - Для каждой строки определяем building_id по коду корпуса
  - Находим или создаём аудиторию (room) в этом корпусе
  - Сохраняем в таблицу schedule_slots
  - Строки с building=online пропускаем
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import Building, Room, ScheduleSlot
from app.integrations.schedule_importer import extract_building_code

logger = logging.getLogger(__name__)

_DEFAULT_ROOM_CAPACITY = 50

# Маппинг кода корпуса на отображаемое имя
_BUILDING_DISPLAY = {
    "Б": "Корпус Б",
    "Р": "Корпус Р",
    "К": "Корпус К",
    "Л": "Корпус Л",
    "С": "Корпус С",
}
_BUILDING_ADDRESS = {
    "Б": "ул. Большая Печерская, 25/12",
    "Р": "ул. Родионова, 136",
    "К": "ул. Козицкого",
    "Л": "ул. Льва Толстого",
    "С": "ул. Сормовское шоссе, 30",
}


async def _load_building_lookup(session: AsyncSession) -> dict[str, int]:
    """Возвращает {код_корпуса: building_id} по именам в БД."""
    result = await session.execute(select(Building))
    lookup: dict[str, int] = {}
    for b in result.scalars().all():
        code = extract_building_code(b.name)
        if code:
            lookup[code] = b.id
    return lookup


async def _get_or_create_building(
    session: AsyncSession,
    code: str,
    lookup: dict[str, int],
) -> int:
    if code in lookup:
        return lookup[code]

    name = _BUILDING_DISPLAY.get(code, f"Корпус {code}")
    address = _BUILDING_ADDRESS.get(code, "")
    building = Building(name=name, address=address)
    session.add(building)
    await session.flush()
    lookup[code] = building.id
    logger.info("Создан корпус: code=%s name=%s id=%s", code, name, building.id)
    return building.id


async def _load_room_lookup(session: AsyncSession) -> dict[tuple[int, str], int]:
    """Возвращает {(building_id, room_name): room_id}."""
    result = await session.execute(select(Room))
    return {(r.building_id, r.name): r.id for r in result.scalars().all()}


async def _get_or_create_room(
    session: AsyncSession,
    building_id: int,
    classroom: str,
    room_lookup: dict[tuple[int, str], int],
) -> int:
    key = (building_id, classroom)
    if key in room_lookup:
        return room_lookup[key]

    room = Room(building_id=building_id, name=classroom, capacity=_DEFAULT_ROOM_CAPACITY, is_active=True)
    session.add(room)
    await session.flush()
    room_lookup[key] = room.id
    logger.info("Создана аудитория: building_id=%s name=%s id=%s", building_id, classroom, room.id)
    return room.id


def _build_datetime(row_date: str, row_time: str) -> datetime:
    d = date.fromisoformat(row_date.strip())
    h, m = map(int, row_time.strip().split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=MOSCOW_TZ)


async def import_hse_csv(
    session: AsyncSession,
    file_path: str | Path,
    replace: bool = True,
) -> dict:
    """Импортирует расписание из HSE CSV файла в таблицу schedule_slots.

    replace=True — удаляет старые записи перед импортом (идемпотентная загрузка).
    Возвращает статистику: {imported, skipped_online, skipped_unknown, errors}.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {path}")

    stats = {"imported": 0, "skipped_online": 0, "skipped_unknown": 0, "errors": 0}

    async with session.begin():
        if replace:
            deleted = await session.execute(delete(ScheduleSlot))
            logger.info("Удалено старых слотов: %s", deleted.rowcount)

        building_lookup = await _load_building_lookup(session)
        room_lookup = await _load_room_lookup(session)

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = {"date", "start_time", "end_time", "classroom", "building"}
            fieldnames = set(reader.fieldnames or [])
            if not required.issubset(fieldnames):
                raise ValueError(
                    f"CSV должен содержать колонки: {', '.join(sorted(required))}. "
                    f"Найдены: {', '.join(sorted(fieldnames))}"
                )

            slots: list[ScheduleSlot] = []
            for lineno, row in enumerate(reader, start=2):
                building_raw = (row.get("building") or "").strip()
                classroom = (row.get("classroom") or "").strip()

                # Пропускаем онлайн-занятия
                if not building_raw or "online" in building_raw.lower():
                    stats["skipped_online"] += 1
                    continue

                building_code = extract_building_code(building_raw)
                if not building_code or not classroom:
                    stats["skipped_unknown"] += 1
                    continue

                try:
                    row_date = date.fromisoformat(row["date"].strip())
                    start_time_str = row["start_time"].strip()
                    end_time_str = row["end_time"].strip()
                    sh, sm = map(int, start_time_str.split(":"))
                    eh, em = map(int, end_time_str.split(":"))
                    start_t = time(sh, sm)
                    end_t = time(eh, em)
                    starts_at = _build_datetime(row["date"], start_time_str)
                    ends_at = _build_datetime(row["date"], end_time_str)
                    if ends_at <= starts_at:
                        stats["errors"] += 1
                        continue
                except (ValueError, KeyError) as exc:
                    logger.warning("Строка %s: ошибка разбора: %s", lineno, exc)
                    stats["errors"] += 1
                    continue

                building_id = await _get_or_create_building(session, building_code, building_lookup)
                room_id = await _get_or_create_room(session, building_id, classroom, room_lookup)

                slots.append(
                    ScheduleSlot(
                        room_id=room_id,
                        date=row_date,
                        start_time=start_t,
                        end_time=end_t,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        subject=(row.get("subject") or "").strip() or None,
                        subject_type=(row.get("subject_type") or "").strip() or None,
                        teacher=(row.get("teacher") or "").strip() or None,
                        group_name=(row.get("group") or "").strip() or None,
                    )
                )
                stats["imported"] += 1

        session.add_all(slots)
        await session.flush()

    logger.info(
        "Импорт завершён: imported=%s skipped_online=%s skipped_unknown=%s errors=%s",
        stats["imported"],
        stats["skipped_online"],
        stats["skipped_unknown"],
        stats["errors"],
    )
    return stats
