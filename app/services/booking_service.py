from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import Booking, ScheduleSlot, User
from app.db.repositories.booking_repo import BookingRepository
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository

MAX_BOOKING_HOURS = 8


class BookingValidationError(Exception):
    """Bad input from the user — bad time range, too long, in the past."""


@dataclass
class BookingConflictError(Exception):
    """Another active booking already covers the requested slot."""

    conflict: Booking

    def __str__(self) -> str:
        return "Аудитория уже занята."


@dataclass
class ScheduleConflictError(Exception):
    """A scheduled class already occupies the room at this time."""

    conflict: ScheduleSlot

    def __str__(self) -> str:
        return "В это время в аудитории занятие по расписанию."


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.room_repo = RoomRepository(session)
        self.booking_repo = BookingRepository(session)

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=MOSCOW_TZ)
        return dt

    def _validate_interval(self, starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
        starts_at = self._ensure_aware(starts_at)
        ends_at = self._ensure_aware(ends_at)

        if starts_at >= ends_at:
            raise BookingValidationError("Окончание должно быть позже начала.")

        now = datetime.now(tz=MOSCOW_TZ)
        if starts_at <= now:
            raise BookingValidationError("Нельзя бронировать на прошедшее время.")

        if (ends_at - starts_at) > timedelta(hours=MAX_BOOKING_HOURS):
            raise BookingValidationError(
                f"Максимальная длительность брони — {MAX_BOOKING_HOURS} часов."
            )

        return starts_at, ends_at

    async def create_booking(
        self,
        user_id: int,
        room_id: int,
        starts_at: datetime,
        ends_at: datetime,
        purpose: str | None,
    ) -> Booking:
        starts_at, ends_at = self._validate_interval(starts_at, ends_at)

        async with self.session.begin():
            user = await self.user_repo.get_by_id(user_id)
            if user is None:
                raise BookingValidationError("Пользователь не найден.")

            room = await self.room_repo.get_room_for_update(room_id)
            if room is None:
                raise BookingValidationError("Аудитория не найдена или недоступна.")

            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:room_id)"),
                {"room_id": room_id},
            )

            schedule_conflict = await self.booking_repo.find_schedule_conflict(
                room_id, starts_at, ends_at,
            )
            if schedule_conflict is not None:
                raise ScheduleConflictError(schedule_conflict)

            booking_conflict = await self.booking_repo.find_active_conflict(
                room_id, starts_at, ends_at,
            )
            if booking_conflict is not None:
                raise BookingConflictError(booking_conflict)

            booking = await self.booking_repo.create_booking(
                user_id=user_id,
                room_id=room_id,
                starts_at=starts_at,
                ends_at=ends_at,
                purpose=purpose,
            )

        return booking

    async def list_user_bookings(self, user_id: int) -> list[Booking]:
        return await self.booking_repo.get_active_user_bookings(user_id)

    async def cancel_booking(self, booking_id: int, actor_user_id: int) -> Booking:
        async with self.session.begin():
            booking = await self.booking_repo.get_with_room(booking_id)
            if booking is None:
                raise BookingValidationError("Бронирование не найдено.")
            if booking.user_id != actor_user_id:
                raise BookingValidationError("Нельзя отменять чужое бронирование.")
            if not booking.is_active:
                raise BookingValidationError("Бронирование уже отменено.")
            booking.is_active = False
        return booking


async def get_conflict_owner(session: AsyncSession, booking: Booking) -> User | None:
    return await session.get(User, booking.user_id)
