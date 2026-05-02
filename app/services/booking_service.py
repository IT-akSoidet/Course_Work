from datetime import datetime
from enum import IntEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.booking_repo import BookingRepository
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository

class RoleId(IntEnum):
    STUDENT = 1
    TEACHER = 2
    ADMIN = 3


class BookingStatusId(IntEnum):
    PENDING = 1
    APPROVED = 2
    REJECTED = 3
    CANCELLED = 4


class BookingConflictError(Exception):
    """Raised when booking cannot be created due to conflict."""


class BookingValidationError(Exception):
    """Raised for invalid booking request payload."""


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.room_repo = RoomRepository(session)
        self.booking_repo = BookingRepository(session)

    async def create_booking(
        self,
        user_id: int,
        room_id: int,
        starts_at: datetime,
        ends_at: datetime,
        purpose: str,
    ):
        now = datetime.now(starts_at.tzinfo) if starts_at.tzinfo else datetime.utcnow()
        if starts_at >= ends_at:
            raise BookingValidationError("Некорректный интервал бронирования.")
        if starts_at <= now:
            raise BookingValidationError("Нельзя бронировать аудиторию в прошедшем времени.")

        user = await self.user_repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise BookingValidationError("Пользователь не найден или деактивирован.")

        async with self.session.begin():
            # Lock room row to serialize competing booking operations.
            room = await self.room_repo.get_room_for_update(room_id)
            if room is None:
                raise BookingValidationError("Аудитория не найдена или недоступна.")

            # Optional advisory lock for extra safety in distributed workers.
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:room_id)"), {"room_id": room_id})

            has_schedule_conflict = await self.room_repo.has_unavailability_conflict(room_id, starts_at, ends_at)
            if has_schedule_conflict:
                raise BookingConflictError("Слот занят по расписанию.")

            has_booking_conflict = await self.booking_repo.has_active_conflict(room_id, starts_at, ends_at)
            priority = 2 if user.role_id == RoleId.TEACHER else 1

            status_id = BookingStatusId.APPROVED
            if has_booking_conflict:
                # Teacher can request override review, student also goes to moderation queue.
                status_id = BookingStatusId.PENDING

            booking = await self.booking_repo.create_booking(
                user_id=user_id,
                room_id=room_id,
                status_id=int(status_id),
                priority=priority,
                starts_at=starts_at,
                ends_at=ends_at,
                purpose=purpose,
            )

        return booking

    async def list_user_bookings(self, user_id: int):
        return await self.booking_repo.get_user_bookings(user_id)

    async def cancel_booking(self, booking_id: int, actor_user_id: int):
        booking = await self.booking_repo.get_by_id(booking_id)
        if booking is None:
            raise BookingValidationError("Бронирование не найдено.")
        if booking.user_id != actor_user_id:
            raise BookingValidationError("Нельзя отменять чужое бронирование.")
        if booking.status_id not in (BookingStatusId.PENDING, BookingStatusId.APPROVED):
            raise BookingValidationError("Бронирование уже неактивно.")

        async with self.session.begin():
            booking.status_id = int(BookingStatusId.CANCELLED)
            await self.session.flush()
        return booking
