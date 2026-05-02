from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Booking
from app.services.booking_service import BookingStatusId, BookingValidationError


class ModerationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_pending(self) -> list[Booking]:
        query = select(Booking).where(Booking.status_id == int(BookingStatusId.PENDING))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def approve(self, booking_id: int, admin_user_id: int) -> Booking:
        return await self._set_status(booking_id, admin_user_id, BookingStatusId.APPROVED, "approve_booking")

    async def reject(self, booking_id: int, admin_user_id: int) -> Booking:
        return await self._set_status(booking_id, admin_user_id, BookingStatusId.REJECTED, "reject_booking")

    async def _set_status(
        self,
        booking_id: int,
        admin_user_id: int,
        status: BookingStatusId,
        audit_action: str,
    ) -> Booking:
        booking = await self.session.get(Booking, booking_id)
        if booking is None:
            raise BookingValidationError("Бронь не найдена.")
        if booking.status_id != int(BookingStatusId.PENDING):
            raise BookingValidationError("Можно модерировать только pending-заявки.")

        async with self.session.begin():
            booking.status_id = int(status)
            self.session.add(
                AuditLog(
                    actor_user_id=admin_user_id,
                    action=audit_action,
                    entity_type="booking",
                    entity_id=str(booking_id),
                    metadata_json=f'{{"new_status":"{status.name.lower()}"}}',
                )
            )
            await self.session.flush()
        return booking
