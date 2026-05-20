from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Booking, Room, ScheduleSlot


class RoomRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_active(self) -> list[Room]:
        query = (
            select(Room)
            .where(Room.is_active.is_(True))
            .options(selectinload(Room.building))
            .order_by(Room.building_id, Room.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_with_building(self, room_id: int) -> Room | None:
        query = (
            select(Room)
            .where(Room.id == room_id)
            .options(selectinload(Room.building))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_room_for_update(self, room_id: int) -> Room | None:
        query = (
            select(Room)
            .where(Room.id == room_id, Room.is_active.is_(True))
            .with_for_update()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search_available_rooms(
        self,
        starts_at: datetime,
        ends_at: datetime,
    ) -> list[Room]:
        booked_rooms = (
            select(Booking.room_id)
            .where(
                Booking.is_active.is_(True),
                Booking.starts_at < ends_at,
                Booking.ends_at > starts_at,
            )
            .subquery()
        )
        scheduled_rooms = (
            select(ScheduleSlot.room_id)
            .where(
                ScheduleSlot.starts_at < ends_at,
                ScheduleSlot.ends_at > starts_at,
            )
            .subquery()
        )
        query = (
            select(Room)
            .where(
                Room.is_active.is_(True),
                Room.id.not_in(select(booked_rooms.c.room_id)),
                Room.id.not_in(select(scheduled_rooms.c.room_id)),
            )
            .options(selectinload(Room.building))
            .order_by(Room.building_id, Room.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
