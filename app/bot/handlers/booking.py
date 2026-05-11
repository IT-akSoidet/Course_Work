from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.parsers import format_dt, format_status, format_time, parse_datetime_input
from app.bot.ui import booking_actions_kb, cancel_kb, format_room_list, main_menu
from app.core.config import get_settings
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.services.booking_service import (
    BookingConflictError,
    BookingService,
    BookingValidationError,
    RoleId,
)

router = Router()


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------

class BookingFlow(StatesGroup):
    waiting_room_id = State()
    waiting_starts_at = State()
    waiting_ends_at = State()
    waiting_purpose = State()


class RoomsSearchFlow(StatesGroup):
    waiting_starts_at = State()
    waiting_ends_at = State()
    waiting_capacity = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ensure_user(telegram_id: int, full_name: str):
    settings = get_settings()
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)
        if user is None:
            role = int(RoleId.ADMIN if telegram_id in settings.admin_telegram_ids else RoleId.STUDENT)
            user = await repo.create(telegram_id=telegram_id, full_name=full_name, role_id=role)
            await session.commit()
        elif telegram_id in settings.admin_telegram_ids and user.role_id != int(RoleId.ADMIN):
            user.role_id = int(RoleId.ADMIN)
            await session.commit()
        return user


def _tg_full_name(message: Message) -> str | None:
    tg = message.from_user
    if tg is None:
        return None
    return tg.full_name or tg.username or f"user_{tg.id}"


def _format_booking(b) -> str:
    return (
        f"<b>Бронь #{b.id}</b>\n"
        f"Аудитория: <code>{b.room_id}</code>\n"
        f"Время: {format_dt(b.starts_at)} — {format_time(b.ends_at)}\n"
        f"Статус: {format_status(b.status_id)}"
    )


async def _room_list_text() -> str:
    async with SessionLocal() as session:
        rooms = await RoomRepository(session).get_all_active()
    if not rooms:
        return "Аудитории ещё не добавлены."
    return format_room_list(rooms)


# ---------------------------------------------------------------------------
# /book  — interactive FSM  or  inline /book id;start;end;purpose
# ---------------------------------------------------------------------------

@router.message(Command("book"))
@router.message(F.text == "Новая бронь")
async def cmd_book(message: Message, state: FSMContext, command: CommandObject | None = None) -> None:
    if command and command.args and ";" in command.args:
        await _inline_booking(message, command.args)
        return

    await state.clear()
    room_text = await _room_list_text()
    await state.set_state(BookingFlow.waiting_room_id)
    await message.answer(
        f"<b>Создание брони</b> (шаг 1/4)\n\n"
        f"{room_text}\n\n"
        f"Введите ID аудитории:",
        reply_markup=cancel_kb(),
    )


async def _inline_booking(message: Message, payload: str) -> None:
    name = _tg_full_name(message)
    if name is None:
        await message.answer("Не удалось определить Telegram ID.")
        return
    user = await _ensure_user(message.from_user.id, name)

    try:
        parts = [p.strip() for p in payload.split(";")]
        if len(parts) < 4:
            raise ValueError
        room_id = int(parts[0])
        starts_at = parse_datetime_input(parts[1])
        ends_at = parse_datetime_input(parts[2])
        purpose = parts[3]
    except (ValueError, IndexError):
        await message.answer(
            "Неверный формат.\n"
            "Пример: <code>/book 10101;2026-05-10 12:00;2026-05-10 14:00;Консультация</code>"
        )
        return

    async with SessionLocal() as session:
        service = BookingService(session)
        try:
            b = await service.create_booking(user.id, room_id, starts_at, ends_at, purpose)
        except (BookingConflictError, BookingValidationError) as exc:
            await message.answer(f"Ошибка: {exc}")
            return

    await message.answer(
        f"Бронь создана!\n\n{_format_booking(b)}\nЦель: {purpose}",
    )


# ---------------------------------------------------------------------------
# /rooms — interactive FSM  or  inline /rooms start;end;capacity
# ---------------------------------------------------------------------------

@router.message(Command("rooms"))
@router.message(F.text == "Найти аудитории")
async def cmd_rooms(message: Message, state: FSMContext, command: CommandObject | None = None) -> None:
    if command and command.args and ";" in command.args:
        await _inline_rooms_search(message, command.args)
        return

    await state.clear()
    await state.set_state(RoomsSearchFlow.waiting_starts_at)
    await message.answer(
        "<b>Поиск аудиторий</b> (шаг 1/3)\n\n"
        "Введите начало интервала:\n"
        "<code>2026-05-10 12:00</code> или <code>10.05.2026 12:00</code>",
        reply_markup=cancel_kb(),
    )


async def _inline_rooms_search(message: Message, payload: str) -> None:
    try:
        parts = [p.strip() for p in payload.split(";")]
        if len(parts) != 3:
            raise ValueError
        starts_at = parse_datetime_input(parts[0])
        ends_at = parse_datetime_input(parts[1])
        min_cap = int(parts[2])
    except (ValueError, IndexError):
        await message.answer(
            "Неверный формат.\n"
            "Пример: <code>/rooms 2026-05-10 12:00;2026-05-10 14:00;20</code>"
        )
        return

    async with SessionLocal() as session:
        rooms = await RoomRepository(session).search_available_rooms(starts_at, ends_at, min_cap)

    if not rooms:
        await message.answer("Свободных аудиторий не найдено.")
        return
    await message.answer("Свободные аудитории:\n\n" + format_room_list(rooms))


# ---------------------------------------------------------------------------
# /my_bookings
# ---------------------------------------------------------------------------

@router.message(Command("my_bookings"))
@router.message(F.text == "Мои брони")
async def cmd_my_bookings(message: Message, state: FSMContext) -> None:
    await state.clear()
    name = _tg_full_name(message)
    if name is None:
        await message.answer("Не удалось определить Telegram ID.")
        return
    user = await _ensure_user(message.from_user.id, name)

    async with SessionLocal() as session:
        bookings = await BookingService(session).list_user_bookings(user.id)

    if not bookings:
        await message.answer("У вас нет активных бронирований.")
        return

    for b in bookings[:20]:
        await message.answer(
            _format_booking(b),
            reply_markup=booking_actions_kb(b.id),
        )


# ---------------------------------------------------------------------------
# /cancel <id>
# ---------------------------------------------------------------------------

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, command: CommandObject) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /cancel &lt;booking_id&gt;")
        return

    name = _tg_full_name(message)
    if name is None:
        await message.answer("Не удалось определить Telegram ID.")
        return
    user = await _ensure_user(message.from_user.id, name)

    booking_id = int(command.args.strip())
    async with SessionLocal() as session:
        try:
            b = await BookingService(session).cancel_booking(booking_id, user.id)
        except BookingValidationError as exc:
            await message.answer(f"Ошибка: {exc}")
            return
    await message.answer(f"Бронь #{b.id} отменена.")


# ---------------------------------------------------------------------------
# /menu, help button
# ---------------------------------------------------------------------------

@router.message(Command("menu"))
@router.message(F.text == "Помощь")
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    settings = get_settings()
    tg = message.from_user
    is_admin = bool(tg and tg.id in settings.admin_telegram_ids)
    await message.answer(
        "/rooms — поиск аудиторий\n"
        "/book — создать бронь\n"
        "/my_bookings — мои брони\n"
        "/help — подробная справка",
        reply_markup=main_menu(is_admin=is_admin),
    )


# ---------------------------------------------------------------------------
# Callback: cancel FSM flow
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "flow:cancel")
async def cb_cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    settings = get_settings()
    is_admin = callback.from_user.id in settings.admin_telegram_ids
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Действие отменено.", reply_markup=main_menu(is_admin=is_admin))
    await callback.answer()


# ---------------------------------------------------------------------------
# Callback: cancel booking from button
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bk:cancel:"))
async def cb_cancel_booking(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer("Сообщение недоступно.", show_alert=True)
        return
    try:
        booking_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    user = await _ensure_user(callback.from_user.id, callback.from_user.full_name)

    async with SessionLocal() as session:
        try:
            await BookingService(session).cancel_booking(booking_id, user.id)
        except BookingValidationError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Бронь #{booking_id} отменена.")
    await callback.answer()


# ---------------------------------------------------------------------------
# FSM: Booking flow steps
# ---------------------------------------------------------------------------

@router.message(BookingFlow.waiting_room_id)
async def fsm_book_room(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите числовой ID аудитории, например <code>10101</code>.")
        return
    await state.update_data(room_id=int(text))
    await state.set_state(BookingFlow.waiting_starts_at)
    await message.answer(
        "<b>Шаг 2/4.</b> Начало бронирования:\n"
        "<code>2026-05-10 12:00</code> или <code>10.05.2026 12:00</code>",
    )


@router.message(BookingFlow.waiting_starts_at)
async def fsm_book_start(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Введите дату и время текстом.")
        return
    try:
        starts_at = parse_datetime_input(message.text)
    except ValueError:
        await message.answer("Не удалось распознать дату. Пример: <code>2026-05-10 12:00</code>")
        return
    await state.update_data(starts_at=starts_at)
    await state.set_state(BookingFlow.waiting_ends_at)
    await message.answer(
        "<b>Шаг 3/4.</b> Окончание бронирования:\n"
        "<code>2026-05-10 14:00</code>",
    )


@router.message(BookingFlow.waiting_ends_at)
async def fsm_book_end(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Введите дату и время текстом.")
        return
    try:
        ends_at = parse_datetime_input(message.text)
    except ValueError:
        await message.answer("Не удалось распознать дату. Пример: <code>2026-05-10 14:00</code>")
        return
    await state.update_data(ends_at=ends_at)
    await state.set_state(BookingFlow.waiting_purpose)
    await message.answer("<b>Шаг 4/4.</b> Цель бронирования (например: «Подготовка к семинару»):")


@router.message(BookingFlow.waiting_purpose)
async def fsm_book_purpose(message: Message, state: FSMContext) -> None:
    purpose = (message.text or "").strip()
    if not purpose:
        await message.answer("Опишите цель бронирования.")
        return

    data = await state.get_data()
    await state.clear()

    name = _tg_full_name(message)
    if name is None:
        await message.answer("Не удалось определить Telegram ID.")
        return
    user = await _ensure_user(message.from_user.id, name)

    async with SessionLocal() as session:
        try:
            b = await BookingService(session).create_booking(
                user_id=user.id,
                room_id=data["room_id"],
                starts_at=data["starts_at"],
                ends_at=data["ends_at"],
                purpose=purpose,
            )
        except (BookingConflictError, BookingValidationError) as exc:
            await message.answer(f"Ошибка: {exc}")
            return

    await message.answer(f"Бронь создана!\n\n{_format_booking(b)}\nЦель: {purpose}")


# ---------------------------------------------------------------------------
# FSM: Rooms search steps
# ---------------------------------------------------------------------------

@router.message(RoomsSearchFlow.waiting_starts_at)
async def fsm_rooms_start(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Введите дату и время текстом.")
        return
    try:
        starts_at = parse_datetime_input(message.text)
    except ValueError:
        await message.answer("Неверный формат. Пример: <code>2026-05-10 12:00</code>")
        return
    await state.update_data(starts_at=starts_at)
    await state.set_state(RoomsSearchFlow.waiting_ends_at)
    await message.answer("<b>Шаг 2/3.</b> Окончание интервала:")


@router.message(RoomsSearchFlow.waiting_ends_at)
async def fsm_rooms_end(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Введите дату и время текстом.")
        return
    try:
        ends_at = parse_datetime_input(message.text)
    except ValueError:
        await message.answer("Неверный формат. Пример: <code>2026-05-10 14:00</code>")
        return
    await state.update_data(ends_at=ends_at)
    await state.set_state(RoomsSearchFlow.waiting_capacity)
    await message.answer("<b>Шаг 3/3.</b> Минимальная вместимость (число):")


@router.message(RoomsSearchFlow.waiting_capacity)
async def fsm_rooms_cap(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите целое число, например <code>20</code>.")
        return

    data = await state.get_data()
    await state.clear()

    async with SessionLocal() as session:
        rooms = await RoomRepository(session).search_available_rooms(
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            min_capacity=int(text),
        )
    if not rooms:
        await message.answer("Свободных аудиторий не найдено.")
        return
    await message.answer("Свободные аудитории:\n\n" + format_room_list(rooms))
