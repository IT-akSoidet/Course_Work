from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BookingStatus, Building, Faculty, Role, Room


async def seed_reference_data(session: AsyncSession) -> None:
    role_exists = await session.scalar(select(Role.id).limit(1))
    if not role_exists:
        await session.execute(
            insert(Role),
            [
                {"id": 1, "name": "student"},
                {"id": 2, "name": "teacher"},
                {"id": 3, "name": "admin"},
            ],
        )

    status_exists = await session.scalar(select(BookingStatus.id).limit(1))
    if not status_exists:
        await session.execute(
            insert(BookingStatus),
            [
                {"id": 1, "name": "pending"},
                {"id": 2, "name": "approved"},
                {"id": 3, "name": "rejected"},
                {"id": 4, "name": "cancelled"},
            ],
        )

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
                {"id": 1, "name": "Корпус Б", "address": "ул. Большая Печерская, 25/12"},
                {"id": 2, "name": "Корпус К", "address": "ул. Родионова, 136"},
                {"id": 3, "name": "Корпус С", "address": "ул. Сормовское ш., 30"},
            ],
        )

    room_exists = await session.scalar(select(Room.id).limit(1))
    if not room_exists:
        await session.execute(
            insert(Room),
            [
                {"id": 10101, "building_id": 1, "name": "101", "capacity": 40, "is_active": True},
                {"id": 10102, "building_id": 1, "name": "102", "capacity": 25, "is_active": True},
                {"id": 10210, "building_id": 1, "name": "210", "capacity": 80, "is_active": True},
                {"id": 20101, "building_id": 2, "name": "101", "capacity": 60, "is_active": True},
                {"id": 20205, "building_id": 2, "name": "205", "capacity": 30, "is_active": True},
                {"id": 30101, "building_id": 3, "name": "101", "capacity": 50, "is_active": True},
            ],
        )
