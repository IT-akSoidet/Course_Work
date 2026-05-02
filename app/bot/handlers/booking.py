from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.services.booking_service import BookingConflictError, BookingService, BookingValidationError

router = Router()


@router.message(Command("book"))
async def cmd_book(message: Message) -> None:
    await message.answer(
        "Создание брони: отправьте данные в формате\n"
        "<room_id>;<YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<purpose>"
    )


@router.message(Command("rooms"))
async def cmd_rooms(message: Message) -> None:
    await message.answer(
        "Поиск аудиторий: /rooms <YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<min_capacity>\n"
        "Пример: /rooms 2026-05-01 12:00;2026-05-01 14:00;20"
    )


@router.message(Command("my_bookings"))
async def cmd_my_bookings(message: Message) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            await message.answer("Вы не зарегистрированы. Обратитесь к администратору.")
            return

        service = BookingService(session)
        bookings = await service.list_user_bookings(user.id)
        if not bookings:
            await message.answer("У вас нет активных бронирований.")
            return

        lines = [
            f"#{b.id}: ауд. {b.room_id}, {b.starts_at:%Y-%m-%d %H:%M} - {b.ends_at:%H:%M}, status={b.status_id}"
            for b in bookings
        ]
        await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    parts = message.text.split() if message.text else []
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Использование: /cancel <booking_id>")
        return

    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return

    booking_id = int(parts[1])
    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            await message.answer("Вы не зарегистрированы. Обратитесь к администратору.")
            return

        service = BookingService(session)
        try:
            booking = await service.cancel_booking(booking_id=booking_id, actor_user_id=user.id)
        except BookingValidationError as exc:
            await message.answer(f"Ошибка отмены: {exc}")
            return
        await message.answer(f"Бронь #{booking.id} отменена.")


def _parse_booking_payload(command_text: str) -> tuple[int, datetime, datetime, str]:
    payload = command_text.replace("/book", "", 1).strip()
    parts = [part.strip() for part in payload.split(";")]
    if len(parts) < 4:
        raise ValueError("Недостаточно данных для бронирования.")
    room_id = int(parts[0])
    starts_at = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
    ends_at = datetime.strptime(parts[2], "%Y-%m-%d %H:%M")
    purpose = parts[3]
    return room_id, starts_at, ends_at, purpose


def _parse_rooms_payload(command_text: str) -> tuple[datetime, datetime, int]:
    payload = command_text.replace("/rooms", "", 1).strip()
    parts = [part.strip() for part in payload.split(";")]
    if len(parts) != 3:
        raise ValueError("Ожидается 3 параметра.")
    starts_at = datetime.strptime(parts[0], "%Y-%m-%d %H:%M")
    ends_at = datetime.strptime(parts[1], "%Y-%m-%d %H:%M")
    min_capacity = int(parts[2])
    return starts_at, ends_at, min_capacity


@router.message()
async def process_booking_payload(message: Message) -> None:
    if not message.text:
        return
    if not message.text.startswith("/book "):
        return

    telegram_id = message.from_user.id if message.from_user else None
    if telegram_id is None:
        await message.answer("Не удалось определить Telegram ID.")
        return

    try:
        room_id, starts_at, ends_at, purpose = _parse_booking_payload(message.text)
    except ValueError:
        await message.answer("Неверный формат. Пример:\n/book 10101;2026-05-01 12:00;2026-05-01 14:00;Консультация")
        return

    async with SessionLocal() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            await message.answer("Вы не зарегистрированы. Обратитесь к администратору.")
            return
        service = BookingService(session)
        try:
            booking = await service.create_booking(user.id, room_id, starts_at, ends_at, purpose)
        except (BookingConflictError, BookingValidationError) as exc:
            await message.answer(f"Ошибка бронирования: {exc}")
            return
        await message.answer(f"Бронь создана: #{booking.id}, status_id={booking.status_id}.")


@router.message()
async def process_rooms_search(message: Message) -> None:
    if not message.text:
        return
    if not message.text.startswith("/rooms "):
        return

    try:
        starts_at, ends_at, min_capacity = _parse_rooms_payload(message.text)
    except ValueError:
        await message.answer("Неверный формат. Пример:\n/rooms 2026-05-01 12:00;2026-05-01 14:00;20")
        return

    async with SessionLocal() as session:
        repo = RoomRepository(session)
        rooms = await repo.search_available_rooms(starts_at, ends_at, min_capacity)
        if not rooms:
            await message.answer("Свободные аудитории не найдены.")
            return
        lines = [f"{room.id}: ауд. {room.name}, вместимость {room.capacity}" for room in rooms[:20]]
        await message.answer("Свободные аудитории:\n" + "\n".join(lines))
