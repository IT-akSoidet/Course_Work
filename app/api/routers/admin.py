from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db_session
from app.services.booking_service import BookingValidationError, RoleId
from app.services.moderation_service import ModerationService
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter

router = APIRouter(prefix="/admin", tags=["admin"])


async def _ensure_admin(session: AsyncSession, admin_user_id: int) -> User:
    admin = await session.get(User, admin_user_id)
    if admin is None or admin.role_id != int(RoleId.ADMIN):
        raise HTTPException(status_code=403, detail="Недостаточно прав.")
    return admin


@router.get("/queue")
async def moderation_queue(admin_user_id: int, session: AsyncSession = Depends(get_db_session)) -> dict:
    await _ensure_admin(session, admin_user_id)
    service = ModerationService(session)
    items = await service.list_pending()
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
    booking_id: int, admin_user_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    await _ensure_admin(session, admin_user_id)
    service = ModerationService(session)
    try:
        booking = await service.approve(booking_id, admin_user_id)
    except BookingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"booking_id": booking.id, "status_id": booking.status_id}


@router.post("/queue/{booking_id}/reject")
async def reject_booking(
    booking_id: int, admin_user_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    await _ensure_admin(session, admin_user_id)
    service = ModerationService(session)
    try:
        booking = await service.reject(booking_id, admin_user_id)
    except BookingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"booking_id": booking.id, "status_id": booking.status_id}


@router.post("/import_schedule")
async def import_schedule(
    csv_path: str, admin_user_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    await _ensure_admin(session, admin_user_id)
    provider = CsvScheduleProvider(csv_path)
    importer = ScheduleImporter(session, provider)
    try:
        count = await importer.import_schedule()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"Ошибка импорта: {exc}") from exc
    return {"imported_slots": count}
