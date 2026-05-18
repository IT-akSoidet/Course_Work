from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Building, Room
from app.db.repositories.room_repo import RoomRepository
from app.integrations.schedule_importer import (
    PublicGoogleSheetsScheduleProvider,
    ScheduleImporter,
    build_room_lookup,
    extract_building_code,
)


@dataclass
class PublicScheduleSyncResult:
    imported_slots: int
    sheet_urls_total: int
    rows_processed: int
    rows_skipped_unknown_room: int
    rows_skipped_online_or_empty: int


async def sync_public_schedule(
    session: AsyncSession,
    *,
    index_url: str | None,
    sheet_urls: list[str],
    source: str = "hse_public_sheets",
    replace_source: bool = True,
) -> PublicScheduleSyncResult:
    rooms = await RoomRepository(session).get_all_active()
    room_lookup = build_room_lookup(rooms)
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup=room_lookup,
        index_url=index_url,
        sheet_urls=sheet_urls,
    )
    importer = ScheduleImporter(session, provider)
    imported = await importer.import_schedule(source=source, replace_source=replace_source)
    return PublicScheduleSyncResult(
        imported_slots=imported,
        sheet_urls_total=provider.stats["sheet_urls_total"],
        rows_processed=provider.stats["rows_processed"],
        rows_skipped_unknown_room=provider.stats["rows_skipped_unknown_room"],
        rows_skipped_online_or_empty=provider.stats["rows_skipped_online_or_empty"],
    )


@dataclass
class PublicScheduleAutofillResult:
    created_buildings: int
    created_rooms: int
    missing_pairs_detected: int
    sync_result: PublicScheduleSyncResult


DEFAULT_BUILDINGS_BY_CODE: dict[str, tuple[str, str]] = {
    "Б": ("Корпус Б", "ул. Большая Печерская, 25/12"),
    "К": ("Корпус К", "ул. Костина, 2Б"),
    "Л": ("Корпус Л", "ул. Львовская, 1В"),
    "Р": ("Корпус Р", "ул. Родионова, 136"),
    "С": ("Корпус С", "ул. Сормовское ш., 30"),
}


async def sync_public_schedule_with_room_autofill(
    session: AsyncSession,
    *,
    index_url: str | None,
    sheet_urls: list[str],
    default_capacity: int = 40,
    source: str = "hse_public_sheets",
) -> PublicScheduleAutofillResult:
    rooms = await RoomRepository(session).get_all_active()
    room_lookup = build_room_lookup(rooms)
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup=room_lookup,
        index_url=index_url,
        sheet_urls=sheet_urls,
    )
    provider.load_slots()
    missing = provider.top_missing_room_pairs(limit=500)

    created_buildings = 0
    created_rooms = 0
    if missing:
        created_buildings, created_rooms = await _create_missing_rooms(
            session=session,
            missing_pairs=[(b, r) for b, r, _ in missing],
            default_capacity=default_capacity,
        )

    sync_result = await sync_public_schedule(
        session=session,
        index_url=index_url,
        sheet_urls=sheet_urls,
        source=source,
        replace_source=True,
    )
    return PublicScheduleAutofillResult(
        created_buildings=created_buildings,
        created_rooms=created_rooms,
        missing_pairs_detected=len(missing),
        sync_result=sync_result,
    )


async def _create_missing_rooms(
    session: AsyncSession,
    missing_pairs: list[tuple[str, str]],
    default_capacity: int,
) -> tuple[int, int]:
    if not missing_pairs:
        return 0, 0

    buildings_result = await session.execute(select(Building))
    buildings = list(buildings_result.scalars().all())
    code_to_building: dict[str, Building] = {}
    for b in buildings:
        code = extract_building_code(b.name) or extract_building_code(b.address)
        if code and code not in code_to_building:
            code_to_building[code] = b

    next_building_id = (await session.scalar(select(func.max(Building.id)))) or 0
    created_buildings = 0
    required_codes = sorted({code for code, _ in missing_pairs if code})
    for code in required_codes:
        if code in code_to_building:
            continue
        next_building_id += 1
        name, address = DEFAULT_BUILDINGS_BY_CODE.get(
            code, (f"Корпус {code}", f"Адрес корпуса {code} (уточнить)")
        )
        b = Building(id=next_building_id, name=name, address=address)
        session.add(b)
        code_to_building[code] = b
        created_buildings += 1
    await session.flush()

    rooms_result = await session.execute(select(Room))
    rooms = list(rooms_result.scalars().all())
    existing_pairs = {(r.building_id, r.name.strip()) for r in rooms}
    next_room_id = (await session.scalar(select(func.max(Room.id)))) or 0

    created_rooms = 0
    for code, room_name in sorted(set(missing_pairs)):
        building = code_to_building.get(code)
        if building is None:
            continue
        key = (building.id, room_name.strip())
        if key in existing_pairs:
            continue
        next_room_id += 1
        session.add(
            Room(
                id=next_room_id,
                building_id=building.id,
                name=room_name.strip(),
                capacity=default_capacity,
                is_active=True,
            )
        )
        existing_pairs.add(key)
        created_rooms += 1

    if created_buildings or created_rooms:
        await session.commit()
    return created_buildings, created_rooms
