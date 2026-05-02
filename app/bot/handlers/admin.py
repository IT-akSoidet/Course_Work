from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter
from app.services.booking_service import BookingValidationError, RoleId
from app.services.moderation_service import ModerationService

router = Router()


@router.message(Command("admin_queue"))
async def cmd_admin_queue(message: Message) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None or user.role_id != int(RoleId.ADMIN):
            await message.answer("Команда доступна только администраторам.")
            return

        pending = await ModerationService(session).list_pending()
        if not pending:
            await message.answer("Очередь модерации пуста.")
            return
        lines = [
            f"#{item.id} | user={item.user_id} | room={item.room_id} | {item.starts_at:%Y-%m-%d %H:%M}-{item.ends_at:%H:%M}"
            for item in pending[:20]
        ]
        await message.answer("Pending заявки:\n" + "\n".join(lines))


@router.message(Command("import_schedule"))
async def cmd_import_schedule(message: Message) -> None:
    parts = message.text.split(maxsplit=1) if message.text else []
    if len(parts) != 2:
        await message.answer("Использование: /import_schedule <path_to_csv>")
        return
    csv_path = parts[1].strip()

    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None or user.role_id != int(RoleId.ADMIN):
            await message.answer("Команда доступна только администраторам.")
            return
        importer = ScheduleImporter(session, CsvScheduleProvider(csv_path))
        try:
            count = await importer.import_schedule()
        except (ValueError, OSError) as exc:
            await message.answer(f"Ошибка импорта: {exc}")
            return

    await message.answer(f"Импорт завершен. Загружено слотов: {count}")


@router.message(Command("approve"))
async def cmd_approve(message: Message) -> None:
    await _handle_decision(message, is_approve=True)


@router.message(Command("reject"))
async def cmd_reject(message: Message) -> None:
    await _handle_decision(message, is_approve=False)


async def _handle_decision(message: Message, is_approve: bool) -> None:
    parts = message.text.split() if message.text else []
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /approve <booking_id> или /reject <booking_id>")
        return
    booking_id = int(parts[1])

    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return

    async with SessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        if user is None or user.role_id != int(RoleId.ADMIN):
            await message.answer("Команда доступна только администраторам.")
            return

        service = ModerationService(session)
        try:
            booking = await (service.approve(booking_id, user.id) if is_approve else service.reject(booking_id, user.id))
        except BookingValidationError as exc:
            await message.answer(f"Ошибка модерации: {exc}")
            return

        action = "подтверждена" if is_approve else "отклонена"
        await message.answer(f"Заявка #{booking.id} {action}.")
