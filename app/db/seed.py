from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Building, Faculty, Room


async def seed_reference_data(session: AsyncSession) -> None:
    faculty_exists = await session.scalar(select(Faculty.id).limit(1))
    if not faculty_exists:
        await session.execute(
            insert(Faculty),
            [
                {"id": 1, "name": "ФКН"},
                {"id": 2, "name": "ФЭН"},
                {"id": 3, "name": "ФГН"},
            ],
        )

    building_exists = await session.scalar(select(Building.id).limit(1))
    if not building_exists:
        await session.execute(
            insert(Building),
            [
                {"id": 1, "name": "Корпус А", "address": "ул. Большая Печерская, 25"},
                {"id": 2, "name": "Корпус Б", "address": "ул. Родионова, 136"},
            ],
        )

    room_exists = await session.scalar(select(Room.id).limit(1))
    if not room_exists:
        await session.execute(
            insert(Room),
            [
                {"id": 10101, "building_id": 1, "name": "101", "capacity": 40, "is_active": True},
                {"id": 10102, "building_id": 1, "name": "102", "capacity": 25, "is_active": True},
                {"id": 20101, "building_id": 2, "name": "201", "capacity": 60, "is_active": True},
            ],
        )
