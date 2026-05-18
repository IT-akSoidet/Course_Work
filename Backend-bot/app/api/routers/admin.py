from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Booking, User
from app.db.session import get_db_session
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter
from app.services.booking_service import BookingStatusId, BookingValidationError, RoleId

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_admin(session: AsyncSession, admin_user_id: int) -> User:
    admin = await session.get(User, admin_user_id)
    if admin is None or admin.role_id != int(RoleId.ADMIN):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")
    return admin


@router.get("/queue")
async def moderation_queue(admin_user_id: int, session: AsyncSession = Depends(get_db_session)) -> dict:
    await _get_admin(session, admin_user_id)
    query = select(Booking).where(Booking.status_id == int(BookingStatusId.PENDING))
    result = await session.execute(query)
    items = list(result.scalars().all())
    return {
        "pending": [
            {
                "booking_id": b.id,
                "user_id": b.user_id,
                "room_id": b.room_id,
                "starts_at": b.starts_at.isoformat(),
                "ends_at": b.ends_at.isoformat(),
                "priority": b.priority,
            }
            for b in items
        ]
    }


@router.post("/queue/{booking_id}/approve")
async def approve_booking(
    booking_id: int, admin_user_id: int, session: AsyncSession = Depends(get_db_session),
) -> dict:
    admin = await _get_admin(session, admin_user_id)
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена.")
    if booking.status_id != int(BookingStatusId.PENDING):
        raise HTTPException(status_code=400, detail="Можно модерировать только заявки на рассмотрении.")

    booking.status_id = int(BookingStatusId.APPROVED)
    session.add(AuditLog(
        actor_user_id=admin.id,
        action="approve_booking",
        entity_type="booking",
        entity_id=str(booking_id),
        metadata_json='{"new_status":"approved"}',
    ))
    await session.commit()
    return {"booking_id": booking.id, "status_id": booking.status_id}


@router.post("/queue/{booking_id}/reject")
async def reject_booking(
    booking_id: int, admin_user_id: int, session: AsyncSession = Depends(get_db_session),
) -> dict:
    admin = await _get_admin(session, admin_user_id)
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена.")
    if booking.status_id != int(BookingStatusId.PENDING):
        raise HTTPException(status_code=400, detail="Можно модерировать только заявки на рассмотрении.")

    booking.status_id = int(BookingStatusId.REJECTED)
    session.add(AuditLog(
        actor_user_id=admin.id,
        action="reject_booking",
        entity_type="booking",
        entity_id=str(booking_id),
        metadata_json='{"new_status":"rejected"}',
    ))
    await session.commit()
    return {"booking_id": booking.id, "status_id": booking.status_id}


@router.post("/import_schedule")
async def import_schedule(
    csv_path: str, admin_user_id: int, session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _get_admin(session, admin_user_id)
    provider = CsvScheduleProvider(file_path=csv_path)
    importer = ScheduleImporter(session, provider)
    try:
        count = await importer.import_schedule()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Ошибка импорта: {exc}") from exc
    return {"imported_slots": count}
