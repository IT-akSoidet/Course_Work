from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Booking, Room, ScheduleSlot


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_active_conflict(
        self, room_id: int, starts_at: datetime, ends_at: datetime,
    ) -> Booking | None:
        query = (
            select(Booking)
            .where(
                Booking.room_id == room_id,
                Booking.is_active.is_(True),
                Booking.starts_at < ends_at,
                Booking.ends_at > starts_at,
            )
            .options(selectinload(Booking.user))
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_schedule_conflict(
        self, room_id: int, starts_at: datetime, ends_at: datetime,
    ) -> ScheduleSlot | None:
        query = (
            select(ScheduleSlot)
            .where(
                ScheduleSlot.room_id == room_id,
                ScheduleSlot.starts_at < ends_at,
                ScheduleSlot.ends_at > starts_at,
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_booking(
        self,
        user_id: int,
        room_id: int,
        starts_at: datetime,
        ends_at: datetime,
        purpose: str | None,
    ) -> Booking:
        booking = Booking(
            user_id=user_id,
            room_id=room_id,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose=purpose,
            is_active=True,
        )
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def get_active_user_bookings(self, user_id: int) -> list[Booking]:
        query = (
            select(Booking)
            .where(Booking.user_id == user_id, Booking.is_active.is_(True))
            .options(selectinload(Booking.room).selectinload(Room.building))
            .order_by(Booking.starts_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, booking_id: int) -> Booking | None:
        return await self.session.get(Booking, booking_id)

    async def get_with_room(self, booking_id: int) -> Booking | None:
        query = (
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.room).selectinload(Room.building))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
