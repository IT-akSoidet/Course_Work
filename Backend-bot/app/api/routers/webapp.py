from datetime import date as date_type
from datetime import datetime, time as time_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import AuditLog, Booking, Building, Room
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.core.config import get_settings
from app.services.booking_service import (
    BookingConflictError,
    BookingService,
    BookingStatusId,
    BookingValidationError,
    RoleId,
)
from app.webapp.auth import WebAppUser, get_webapp_user

router = APIRouter(prefix="/api", tags=["webapp"])


class BookingCreateRequest(BaseModel):
    room_id: int
    starts_at: datetime
    ends_at: datetime
    purpose: str = Field(default="", max_length=500)


def _status_label(status_id: int) -> str:
    return {
        int(BookingStatusId.PENDING): "На рассмотрении",
        int(BookingStatusId.APPROVED): "Подтверждено",
        int(BookingStatusId.REJECTED): "Отклонено",
        int(BookingStatusId.CANCELLED): "Отменено",
    }.get(status_id, f"Статус #{status_id}")


async def _resolve_actor(session: AsyncSession, webapp_user: WebAppUser):
    settings = get_settings()
    repo = UserRepository(session)
    user = await repo.get_by_telegram_id(webapp_user.telegram_id)
    if user is None:
        role = int(RoleId.ADMIN if webapp_user.telegram_id in settings.admin_telegram_ids else RoleId.STUDENT)
        user = await repo.create(
            telegram_id=webapp_user.telegram_id,
            full_name=webapp_user.full_name,
            role_id=role,
        )
        await session.commit()
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь деактивирован.")
    elif webapp_user.telegram_id in settings.admin_telegram_ids and user.role_id != int(RoleId.ADMIN):
        user.role_id = int(RoleId.ADMIN)
        await session.commit()
    return user


def _booking_to_payload(booking: Booking) -> dict:
    return {
        "booking_id": booking.id,
        "room_id": booking.room_id,
        "starts_at": booking.starts_at.isoformat(),
        "ends_at": booking.ends_at.isoformat(),
        "purpose": booking.purpose or "",
        "status_id": booking.status_id,
        "status_label": _status_label(booking.status_id),
    }


@router.get("/buildings")
async def get_buildings(session: AsyncSession = Depends(get_db_session)) -> dict:
    result = await session.execute(select(Building).order_by(Building.name))
    buildings = result.scalars().all()
    return {
        "buildings": [
            {"id": b.id, "name": b.name}
            for b in buildings
        ]
    }


@router.get("/rooms/free")
async def webapp_free_rooms(
    date: date_type,
    start_time: str,
    end_time: str,
    building: str | None = None,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Свободные аудитории по дате и времени в формате ВШЭ.

    Параметры: date=2025-04-06, start_time=08:00, end_time=09:20, building=БП
    """
    _ = await _resolve_actor(session=session, webapp_user=webapp_user)

    # Разбираем HH:MM строки
    try:
        sh, sm = map(int, start_time.split(":"))
        eh, em = map(int, end_time.split(":"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Формат времени: HH:MM") from exc

    starts_at = datetime(date.year, date.month, date.day, sh, sm, tzinfo=MOSCOW_TZ)
    ends_at = datetime(date.year, date.month, date.day, eh, em, tzinfo=MOSCOW_TZ)

    if ends_at <= starts_at:
        raise HTTPException(status_code=400, detail="end_time должен быть позже start_time.")

    # Опциональная фильтрация по корпусу (принимаем и строку-код "БП", и id)
    building_id: int | None = None
    if building:
        result_b = await session.execute(select(Building))
        from app.integrations.schedule_importer import extract_building_code
        code = extract_building_code(building)
        for b in result_b.scalars().all():
            from app.integrations.schedule_importer import extract_building_code as ebc
            if ebc(b.name) == code:
                building_id = b.id
                break

    rooms = await RoomRepository(session).search_available_rooms(
        starts_at=starts_at,
        ends_at=ends_at,
        building_id=building_id,
    )
    return {
        "rooms": [
            {
                "id": room.id,
                "name": room.name,
                "capacity": room.capacity,
                "building_id": room.building_id,
                "building_name": room.building.name,
            }
            for room in rooms
        ]
    }


@router.get("/rooms/available")
async def webapp_available_rooms(
    starts_at: datetime,
    ends_at: datetime,
    building_id: int | None = None,
    min_capacity: int = 1,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    _ = await _resolve_actor(session=session, webapp_user=webapp_user)
    rooms = await RoomRepository(session).search_available_rooms(
        starts_at=starts_at,
        ends_at=ends_at,
        min_capacity=min_capacity,
        building_id=building_id,
    )
    return {
        "rooms": [
            {
                "id": room.id,
                "name": room.name,
                "capacity": room.capacity,
                "building_id": room.building_id,
                "building_name": room.building.name,
            }
            for room in rooms
        ]
    }


@router.get("/bootstrap")
async def webapp_bootstrap(
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    rooms = await RoomRepository(session).get_all_active()
    result = await session.execute(select(Building).order_by(Building.name))
    buildings = result.scalars().all()
    return {
        "user": {
            "id": actor.id,
            "telegram_id": actor.telegram_id,
            "full_name": actor.full_name,
            "role_id": actor.role_id,
        },
        "buildings": [{"id": b.id, "name": b.name} for b in buildings],
        "rooms": [
            {
                "id": room.id,
                "name": room.name,
                "capacity": room.capacity,
                "building_id": room.building_id,
                "building_name": room.building.name,
            }
            for room in rooms
        ],
    }


@router.post("/bookings")
async def webapp_create_booking(
    payload: BookingCreateRequest,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    actor_id = actor.id
    if session.in_transaction():
        await session.rollback()
    service = BookingService(session)
    try:
        booking = await service.create_booking(
            user_id=actor_id,
            room_id=payload.room_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            purpose=payload.purpose,
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BookingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _booking_to_payload(booking)


@router.get("/bookings/my")
async def webapp_my_bookings(
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    items = await BookingService(session).list_user_bookings(actor.id)
    return {"bookings": [_booking_to_payload(item) for item in items]}


@router.delete("/bookings/{booking_id}")
async def webapp_cancel_booking(
    booking_id: int,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    actor_id = actor.id
    if session.in_transaction():
        await session.rollback()
    try:
        booking = await BookingService(session).cancel_booking(booking_id=booking_id, actor_user_id=actor_id)
    except BookingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _booking_to_payload(booking)


@router.get("/admin/queue")
async def webapp_admin_queue(
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    if actor.role_id != int(RoleId.ADMIN):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    query = select(Booking).where(Booking.status_id == int(BookingStatusId.PENDING)).order_by(Booking.created_at)
    result = await session.execute(query)
    items = result.scalars().all()
    return {"pending": [_booking_to_payload(item) for item in items]}


@router.post("/admin/queue/{booking_id}/approve")
async def webapp_admin_approve(
    booking_id: int,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    if actor.role_id != int(RoleId.ADMIN):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена.")
    if booking.status_id != int(BookingStatusId.PENDING):
        raise HTTPException(status_code=400, detail="Можно модерировать только заявки на рассмотрении.")
    booking.status_id = int(BookingStatusId.APPROVED)
    session.add(
        AuditLog(
            actor_user_id=actor.id,
            action="approve_booking_webapp",
            entity_type="booking",
            entity_id=str(booking_id),
            metadata_json='{"new_status":"approved"}',
        )
    )
    await session.commit()
    return _booking_to_payload(booking)


@router.post("/admin/queue/{booking_id}/reject")
async def webapp_admin_reject(
    booking_id: int,
    webapp_user: WebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    actor = await _resolve_actor(session=session, webapp_user=webapp_user)
    if actor.role_id != int(RoleId.ADMIN):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")

    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена.")
    if booking.status_id != int(BookingStatusId.PENDING):
        raise HTTPException(status_code=400, detail="Можно модерировать только заявки на рассмотрении.")
    booking.status_id = int(BookingStatusId.REJECTED)
    session.add(
        AuditLog(
            actor_user_id=actor.id,
            action="reject_booking_webapp",
            entity_type="booking",
            entity_id=str(booking_id),
            metadata_json='{"new_status":"rejected"}',
        )
    )
    await session.commit()
    return _booking_to_payload(booking)
