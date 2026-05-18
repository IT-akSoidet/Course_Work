from datetime import datetime
from enum import IntEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
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
    pass


class BookingValidationError(Exception):
    pass


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
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=MOSCOW_TZ)
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=MOSCOW_TZ)

        now = datetime.now(tz=MOSCOW_TZ)
        if starts_at >= ends_at:
            raise BookingValidationError("Начало должно быть раньше окончания.")
        if starts_at <= now:
            raise BookingValidationError("Нельзя бронировать в прошедшем времени.")

        async with self.session.begin():
            user = await self.user_repo.get_by_id(user_id)
            if user is None or not user.is_active:
                raise BookingValidationError("Пользователь не найден или деактивирован.")

            room = await self.room_repo.get_room_for_update(room_id)
            if room is None:
                raise BookingValidationError("Аудитория не найдена или недоступна.")

            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:room_id)"),
                {"room_id": room_id},
            )

            # Проверяем занятость по расписанию (CSV-импорт)
            has_schedule_conflict = await self.room_repo.has_schedule_conflict(
                room_id, starts_at, ends_at,
            )
            if has_schedule_conflict:
                raise BookingConflictError("Время занято по расписанию пар.")

            # Проверяем ручные блокировки (Google Sheets синхронизация)
            has_unavailability = await self.room_repo.has_unavailability_conflict(
                room_id, starts_at, ends_at,
            )
            if has_unavailability:
                raise BookingConflictError("Аудитория недоступна в это время.")

            has_booking_conflict = await self.booking_repo.has_active_conflict(
                room_id, starts_at, ends_at,
            )
            priority = 2 if user.role_id == RoleId.TEACHER else 1
            status_id = BookingStatusId.APPROVED
            if has_booking_conflict:
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
        async with self.session.begin():
            booking = await self.booking_repo.get_by_id(booking_id)
            if booking is None:
                raise BookingValidationError("Бронирование не найдено.")
            if booking.user_id != actor_user_id:
                raise BookingValidationError("Нельзя отменять чужое бронирование.")
            if booking.status_id not in (BookingStatusId.PENDING, BookingStatusId.APPROVED):
                raise BookingValidationError("Бронирование уже неактивно.")
            booking.status_id = int(BookingStatusId.CANCELLED)
            await self.session.flush()
        return booking
