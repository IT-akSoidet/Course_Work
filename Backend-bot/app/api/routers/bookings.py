from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.booking_service import BookingConflictError, BookingService, BookingValidationError

router = APIRouter(prefix="/bookings", tags=["bookings"])


class BookingCreateRequest(BaseModel):
    user_id: int
    room_id: int
    starts_at: datetime
    ends_at: datetime
    purpose: str = Field(default="", max_length=500)


@router.post("")
async def create_booking(payload: BookingCreateRequest, session: AsyncSession = Depends(get_db_session)) -> dict:
    service = BookingService(session)
    try:
        booking = await service.create_booking(
            user_id=payload.user_id,
            room_id=payload.room_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            purpose=payload.purpose,
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BookingValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"booking_id": booking.id, "status_id": booking.status_id}
