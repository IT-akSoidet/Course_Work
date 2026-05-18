from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Booking, Room, RoomUnavailability, ScheduleSlot


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

    async def get_room_for_update(self, room_id: int) -> Room | None:
        query = select(Room).where(Room.id == room_id, Room.is_active.is_(True)).with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def has_schedule_conflict(self, room_id: int, starts_at: datetime, ends_at: datetime) -> bool:
        """Проверяет конфликт с учебным расписанием (таблица schedule_slots)."""
        query = (
            select(ScheduleSlot.id)
            .where(
                ScheduleSlot.room_id == room_id,
                ScheduleSlot.starts_at < ends_at,
                ScheduleSlot.ends_at > starts_at,
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def has_unavailability_conflict(self, room_id: int, starts_at: datetime, ends_at: datetime) -> bool:
        """Проверяет конфликт с ручными блокировками (таблица room_unavailability)."""
        query = (
            select(RoomUnavailability.id)
            .where(
                RoomUnavailability.room_id == room_id,
                RoomUnavailability.starts_at < ends_at,
                RoomUnavailability.ends_at > starts_at,
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def search_available_rooms(
        self,
        starts_at: datetime,
        ends_at: datetime,
        min_capacity: int = 1,
        building_id: int | None = None,
    ) -> list[Room]:
        """Возвращает аудитории, свободные в указанный промежуток.

        Аудитория считается занятой, если:
        - есть активное бронирование в это время (bookings)
        - есть занятие по расписанию (schedule_slots)
        - есть ручная блокировка (room_unavailability)
        """
        # Подзапрос: аудитории с активными бронированиями
        booked_subquery = (
            select(Booking.room_id)
            .where(
                Booking.starts_at < ends_at,
                Booking.ends_at > starts_at,
                Booking.status_id.in_([1, 2]),
            )
            .subquery()
        )
        # Подзапрос: аудитории с занятиями по расписанию
        scheduled_subquery = (
            select(ScheduleSlot.room_id)
            .where(
                ScheduleSlot.starts_at < ends_at,
                ScheduleSlot.ends_at > starts_at,
            )
            .subquery()
        )
        # Подзапрос: аудитории с ручными блокировками
        unavailable_subquery = (
            select(RoomUnavailability.room_id)
            .where(
                RoomUnavailability.starts_at < ends_at,
                RoomUnavailability.ends_at > starts_at,
            )
            .subquery()
        )

        filters = [
            Room.is_active.is_(True),
            Room.capacity >= min_capacity,
            Room.id.not_in(select(booked_subquery.c.room_id)),
            Room.id.not_in(select(scheduled_subquery.c.room_id)),
            Room.id.not_in(select(unavailable_subquery.c.room_id)),
        ]
        if building_id is not None:
            filters.append(Room.building_id == building_id)

        query = (
            select(Room)
            .where(*filters)
            .options(selectinload(Room.building))
            .order_by(Room.name.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
