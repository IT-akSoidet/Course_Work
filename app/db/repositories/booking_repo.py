from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Booking


class BookingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def has_active_conflict(self, room_id: int, starts_at: datetime, ends_at: datetime) -> bool:
        query = (
            select(Booking.id)
            .where(
                Booking.room_id == room_id,
                Booking.starts_at < ends_at,
                Booking.ends_at > starts_at,
                Booking.status_id.in_([1, 2]),
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def create_booking(
        self,
        user_id: int,
        room_id: int,
        status_id: int,
        priority: int,
        starts_at: datetime,
        ends_at: datetime,
        purpose: str,
    ) -> Booking:
        booking = Booking(
            user_id=user_id,
            room_id=room_id,
            status_id=status_id,
            priority=priority,
            starts_at=starts_at,
            ends_at=ends_at,
            purpose=purpose,
        )
        self.session.add(booking)
        await self.session.flush()
        return booking

    async def get_user_bookings(self, user_id: int) -> list[Booking]:
        query = (
            select(Booking)
            .where(Booking.user_id == user_id, Booking.status_id.in_([1, 2]))
            .order_by(Booking.starts_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending(self) -> list[Booking]:
        query = select(Booking).where(Booking.status_id == 1).order_by(Booking.created_at.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, booking_id: int) -> Booking | None:
        return await self.session.get(Booking, booking_id)
