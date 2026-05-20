from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.single_message import (
    clear_state_keep_main,
    delete_user_message,
    edit_or_create_main,
    remember_main_from_callback,
)
from app.bot.parsers import (
    combine_date_time,
    format_date_human,
    format_dt,
    format_time,
    parse_time,
)
from app.bot.ui import (
    back_cancel_kb,
    booking_created_kb,
    cancel_confirm_kb,
    cancel_done_kb,
    date_picker_kb,
    empty_bookings_kb,
    format_booking_card,
    format_free_summary,
    my_bookings_kb,
    rooms_list_kb,
    to_home_only_kb,
)
from app.core.config import MOSCOW_TZ, get_settings
from app.db.repositories.booking_repo import BookingRepository
from app.db.repositories.room_repo import RoomRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.services.booking_service import (
    BookingConflictError,
    BookingService,
    BookingValidationError,
    ScheduleConflictError,
)
from app.services.free_slots import (
    FreeWindow,
    find_window_for,
    format_windows,
    get_free_windows,
    list_rooms_with_windows,
)

router = Router()


# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------

class BookingFlow(StatesGroup):
    choosing_date = State()
    choosing_room = State()
    entering_start = State()
    entering_end = State()
    entering_purpose = State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tg_full_name(message: Message | CallbackQuery) -> str:
    tg = message.from_user
    if tg is None:
        return "user"
    return tg.full_name or tg.username or f"user_{tg.id}"


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_settings().admin_telegram_ids


async def _ensure_user(tg_id: int, full_name: str, username: str | None):
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.upsert(tg_id, full_name, username)
        await session.commit()
        return user


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _serialize_windows(windows: list[FreeWindow]) -> list[list[str]]:
    return [[w.start.strftime("%H:%M"), w.end.strftime("%H:%M")] for w in windows]


def _deserialize_windows(raw: list[list[str]] | None) -> list[FreeWindow]:
    if not raw:
        return []
    return [FreeWindow(start=parse_time(s), end=parse_time(e)) for s, e in raw]


# ---------------------------------------------------------------------------
# Step rendering
# ---------------------------------------------------------------------------

async def _render_date_picker(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await edit_or_create_main(
        bot, chat_id, state,
        "<b>📝 Создание брони</b>\n\nВыберите дату:",
        reply_markup=date_picker_kb("book"),
    )


async def _render_summary_step(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    on_date: date,
) -> bool:
    """Render date-summary + room buttons. Returns True if rooms were available."""
    async with SessionLocal() as session:
        rooms_with_windows = await list_rooms_with_windows(session, on_date)

    header = (
        f"<b>📝 Создание брони</b>\n"
        f"📅 <b>{format_date_human(on_date)}</b>"
    )
    text = format_free_summary(rooms_with_windows, header)
    rooms = [r for r, _ in rooms_with_windows]

    if rooms:
        text += "\n\nВыберите аудиторию:"
        await edit_or_create_main(
            bot, chat_id, state, text, reply_markup=rooms_list_kb(rooms, "book"),
        )
        return True

    text += "\n\nПопробуйте другую дату."
    await edit_or_create_main(bot, chat_id, state, text, reply_markup=to_home_only_kb())
    return False


async def _render_start_step(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    windows = _deserialize_windows(data.get("windows"))
    await edit_or_create_main(
        bot, chat_id, state,
        f"<b>📝 Создание брони</b>\n"
        f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
        f"🕐 Свободно: {format_windows(windows)}\n\n"
        f"Введите время начала (ЧЧ:ММ):",
        reply_markup=back_cancel_kb("book"),
    )


async def _render_end_step(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    windows = _deserialize_windows(data.get("windows"))
    start_t = parse_time(data["start_time"])
    window = next((w for w in windows if w.contains(start_t)), None)
    free_until = window.end.strftime("%H:%M") if window else format_windows(windows)
    await edit_or_create_main(
        bot, chat_id, state,
        f"<b>📝 Создание брони</b>\n"
        f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
        f"⏰ Начало: {start_t.strftime('%H:%M')} | Свободно до: {free_until}\n\n"
        f"Введите время окончания (ЧЧ:ММ):",
        reply_markup=back_cancel_kb("book"),
    )


async def _render_purpose_step(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    start_t = parse_time(data["start_time"])
    end_t = parse_time(data["end_time"])
    await edit_or_create_main(
        bot, chat_id, state,
        f"<b>📝 Создание брони</b>\n"
        f"📅 {format_date_human(chosen_date)}, "
        f"{start_t.strftime('%H:%M')}–{end_t.strftime('%H:%M')} | 📍 {data['room_label']}\n\n"
        f"Введите цель бронирования:",
        reply_markup=back_cancel_kb("book"),
    )


# ---------------------------------------------------------------------------
# /book — entry points
# ---------------------------------------------------------------------------

@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext) -> None:
    await delete_user_message(message)
    await clear_state_keep_main(state)
    await _render_date_picker(message.bot, message.chat.id, state)
    await state.set_state(BookingFlow.choosing_date)


@router.callback_query(F.data == "act:book")
async def cb_act_book(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_state_keep_main(state)
    await remember_main_from_callback(state, callback.message.message_id)
    await _render_date_picker(callback.bot, callback.message.chat.id, state)
    await state.set_state(BookingFlow.choosing_date)


# ---------------------------------------------------------------------------
# /book — FSM transitions
# ---------------------------------------------------------------------------

@router.callback_query(BookingFlow.choosing_date, F.data.startswith("book:date:"))
async def cb_book_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    raw = callback.data.split(":", 2)[2]
    chosen_date = _parse_iso_date(raw)
    await remember_main_from_callback(state, callback.message.message_id)
    await state.update_data(date=chosen_date.isoformat())

    has_rooms = await _render_summary_step(
        callback.bot, callback.message.chat.id, state, chosen_date,
    )

    if has_rooms:
        await state.set_state(BookingFlow.choosing_room)
    else:
        await clear_state_keep_main(state)


@router.callback_query(BookingFlow.choosing_room, F.data.startswith("book:room:"))
async def cb_book_room(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    room_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])

    async with SessionLocal() as session:
        room = await RoomRepository(session).get_with_building(room_id)
        windows = await get_free_windows(session, room_id, chosen_date)

    if room is None:
        await callback.answer("Аудитория не найдена.", show_alert=True)
        return
    if not windows:
        await callback.answer("Аудитория уже занята на весь день.", show_alert=True)
        return

    await remember_main_from_callback(state, callback.message.message_id)
    await state.update_data(
        room_id=room_id,
        room_label=f"Ауд. {room.name}, {room.building.name}",
        windows=_serialize_windows(windows),
    )
    await state.set_state(BookingFlow.entering_start)
    await _render_start_step(callback.bot, callback.message.chat.id, state)


@router.message(BookingFlow.entering_start)
async def fsm_book_start(message: Message, state: FSMContext) -> None:
    text_in = message.text or ""
    await delete_user_message(message)

    try:
        start_t = parse_time(text_in)
    except ValueError as exc:
        data = await state.get_data()
        windows = _deserialize_windows(data.get("windows"))
        chosen_date = _parse_iso_date(data["date"])
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            f"<b>📝 Создание брони</b>\n"
            f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
            f"🕐 Свободно: {format_windows(windows)}\n\n"
            f"❌ {exc}\nВведите время начала (ЧЧ:ММ):",
            reply_markup=back_cancel_kb("book"),
        )
        return

    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    windows = _deserialize_windows(data.get("windows"))
    starts_at = combine_date_time(chosen_date, start_t)
    now = datetime.now(tz=MOSCOW_TZ)
    if starts_at <= now:
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            f"<b>📝 Создание брони</b>\n"
            f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
            f"🕐 Свободно: {format_windows(windows)}\n\n"
            f"❌ Время начала уже прошло.\nВведите более позднее время:",
            reply_markup=back_cancel_kb("book"),
        )
        return

    window = next((w for w in windows if w.contains(start_t)), None)
    if window is None:
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            f"<b>📝 Создание брони</b>\n"
            f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
            f"🕐 Свободно: {format_windows(windows)}\n\n"
            f"❌ В это время аудитория занята.\n"
            f"Введите время начала из свободного окна:",
            reply_markup=back_cancel_kb("book"),
        )
        return

    await state.update_data(start_time=start_t.strftime("%H:%M"))
    await state.set_state(BookingFlow.entering_end)
    await _render_end_step(message.bot, message.chat.id, state)


@router.message(BookingFlow.entering_end)
async def fsm_book_end(message: Message, state: FSMContext) -> None:
    text_in = message.text or ""
    await delete_user_message(message)

    try:
        end_t = parse_time(text_in)
    except ValueError as exc:
        data = await state.get_data()
        chosen_date = _parse_iso_date(data["date"])
        windows = _deserialize_windows(data.get("windows"))
        start_t = parse_time(data["start_time"])
        window = next((w for w in windows if w.contains(start_t)), None)
        free_until = window.end.strftime("%H:%M") if window else format_windows(windows)
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            f"<b>📝 Создание брони</b>\n"
            f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
            f"⏰ Начало: {start_t.strftime('%H:%M')} | Свободно до: {free_until}\n\n"
            f"❌ {exc}\nВведите время окончания (ЧЧ:ММ):",
            reply_markup=back_cancel_kb("book"),
        )
        return

    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    windows = _deserialize_windows(data.get("windows"))
    start_t = parse_time(data["start_time"])
    window_active = next((w for w in windows if w.contains(start_t)), None)
    free_until = window_active.end.strftime("%H:%M") if window_active else format_windows(windows)

    def fail(msg: str) -> str:
        return (
            f"<b>📝 Создание брони</b>\n"
            f"📅 {format_date_human(chosen_date)} | 📍 {data['room_label']}\n"
            f"⏰ Начало: {start_t.strftime('%H:%M')} | Свободно до: {free_until}\n\n"
            f"❌ {msg}\nВведите время окончания (ЧЧ:ММ):"
        )

    if end_t <= start_t:
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            fail("Время окончания должно быть позже начала."),
            reply_markup=back_cancel_kb("book"),
        )
        return

    if (end_t.hour * 60 + end_t.minute) - (start_t.hour * 60 + start_t.minute) > 8 * 60:
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            fail("Максимальная длительность брони — 8 часов."),
            reply_markup=back_cancel_kb("book"),
        )
        return

    if find_window_for(windows, start_t, end_t) is None:
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            fail("В это время аудитория занята."),
            reply_markup=back_cancel_kb("book"),
        )
        return

    await state.update_data(end_time=end_t.strftime("%H:%M"))
    await state.set_state(BookingFlow.entering_purpose)
    await _render_purpose_step(message.bot, message.chat.id, state)


@router.message(BookingFlow.entering_purpose)
async def fsm_book_purpose(message: Message, state: FSMContext) -> None:
    purpose = (message.text or "").strip()
    await delete_user_message(message)

    if not purpose:
        await _render_purpose_step(message.bot, message.chat.id, state)
        return

    data = await state.get_data()
    chosen_date = _parse_iso_date(data["date"])
    start_t = parse_time(data["start_time"])
    end_t = parse_time(data["end_time"])
    starts_at = combine_date_time(chosen_date, start_t)
    ends_at = combine_date_time(chosen_date, end_t)
    room_id = data["room_id"]
    bot = message.bot
    chat_id = message.chat.id

    tg = message.from_user
    user = await _ensure_user(tg.id, _tg_full_name(message), tg.username)

    async with SessionLocal() as session:
        service = BookingService(session)
        try:
            booking = await service.create_booking(
                user_id=user.id,
                room_id=room_id,
                starts_at=starts_at,
                ends_at=ends_at,
                purpose=purpose,
            )
        except BookingConflictError as exc:
            owner_user = exc.conflict.user
            owner_name = owner_user.full_name if owner_user else "—"
            owner_uname = f" (@{owner_user.username})" if owner_user and owner_user.username else ""
            await edit_or_create_main(
                bot, chat_id, state,
                "❌ <b>Аудитория уже занята</b>\n\n"
                f"Владелец: {owner_name}{owner_uname}\n"
                f"📅 {format_dt(exc.conflict.starts_at)}–{format_time(exc.conflict.ends_at)}",
                reply_markup=to_home_only_kb(),
            )
            await clear_state_keep_main(state)
            return
        except ScheduleConflictError as exc:
            slot = exc.conflict
            teacher_line = f"\n👨‍🏫 {slot.teacher}" if slot.teacher else ""
            await edit_or_create_main(
                bot, chat_id, state,
                "❌ <b>В это время в аудитории занятие по расписанию</b>\n\n"
                f"📚 {slot.subject}{teacher_line}\n"
                f"📅 {format_dt(slot.starts_at)}–{format_time(slot.ends_at)}",
                reply_markup=to_home_only_kb(),
            )
            await clear_state_keep_main(state)
            return
        except BookingValidationError as exc:
            await edit_or_create_main(
                bot, chat_id, state, f"❌ {exc}", reply_markup=to_home_only_kb(),
            )
            await clear_state_keep_main(state)
            return

    async with SessionLocal() as fetch_session:
        booking_full = await BookingRepository(fetch_session).get_with_room(booking.id)

    await clear_state_keep_main(state)
    await edit_or_create_main(
        bot, chat_id, state,
        "✅ <b>Бронирование создано!</b>\n\n" + format_booking_card(booking_full),
        reply_markup=booking_created_kb(booking_full.id),
    )


# ---------------------------------------------------------------------------
# /book — back/cancel
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "book:cancel")
async def cb_book_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_state_keep_main(state)
    await remember_main_from_callback(state, callback.message.message_id)
    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state,
        "Действие отменено.",
        reply_markup=to_home_only_kb(),
    )


@router.callback_query(F.data == "book:back")
async def cb_book_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    current = await state.get_state()
    bot = callback.bot
    chat_id = callback.message.chat.id
    await remember_main_from_callback(state, callback.message.message_id)

    if current == BookingFlow.choosing_room.state:
        await state.set_state(BookingFlow.choosing_date)
        await _render_date_picker(bot, chat_id, state)
    elif current == BookingFlow.entering_start.state:
        data = await state.get_data()
        chosen_date = _parse_iso_date(data["date"])
        await state.update_data(room_id=None, room_label=None, windows=None)
        await _render_summary_step(bot, chat_id, state, chosen_date)
        await state.set_state(BookingFlow.choosing_room)
    elif current == BookingFlow.entering_end.state:
        await state.set_state(BookingFlow.entering_start)
        await state.update_data(start_time=None)
        await _render_start_step(bot, chat_id, state)
    elif current == BookingFlow.entering_purpose.state:
        await state.set_state(BookingFlow.entering_end)
        await state.update_data(end_time=None)
        await _render_end_step(bot, chat_id, state)


# ---------------------------------------------------------------------------
# /my_bookings — pagination + cancellation flow
# ---------------------------------------------------------------------------

async def _render_my_bookings(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    user_id: int,
    idx: int,
) -> None:
    async with SessionLocal() as session:
        bookings = await BookingService(session).list_user_bookings(user_id)

    if not bookings:
        await edit_or_create_main(
            bot, chat_id, state,
            "📋 <b>У вас нет активных броней</b>",
            reply_markup=empty_bookings_kb(),
        )
        return

    idx = max(0, min(idx, len(bookings) - 1))
    booking = bookings[idx]
    text = (
        f"📋 Бронь <b>{idx + 1}</b> из <b>{len(bookings)}</b>\n\n"
        + format_booking_card(booking)
    )
    await edit_or_create_main(
        bot, chat_id, state, text,
        reply_markup=my_bookings_kb(booking.id, idx, len(bookings)),
    )


@router.message(Command("my_bookings"))
async def cmd_my_bookings(message: Message, state: FSMContext) -> None:
    await delete_user_message(message)
    await clear_state_keep_main(state)
    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_user(tg.id, _tg_full_name(message), tg.username)
    await _render_my_bookings(message.bot, message.chat.id, state, user.id, idx=0)


@router.callback_query(F.data == "act:my")
async def cb_act_my(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_state_keep_main(state)
    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )
    await _render_my_bookings(
        callback.bot, callback.message.chat.id, state, user.id, idx=0,
    )


@router.callback_query(F.data.startswith("booking_page:"))
async def cb_booking_page(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        idx = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректный индекс.", show_alert=True)
        return

    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )
    await _render_my_bookings(
        callback.bot, callback.message.chat.id, state, user.id, idx,
    )


@router.callback_query(F.data.startswith("booking_cancel:"))
async def cb_booking_cancel_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    booking_id = int(parts[1])
    idx = int(parts[2])

    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )

    async with SessionLocal() as session:
        booking = await BookingRepository(session).get_with_room(booking_id)

    if booking is None or booking.user_id != user.id or not booking.is_active:
        await callback.answer("Эта бронь уже недоступна.", show_alert=True)
        await _render_my_bookings(
            callback.bot, callback.message.chat.id, state, user.id, idx,
        )
        return

    text = (
        f"📋 Бронь #<b>{booking.id}</b>\n\n"
        + format_booking_card(booking)
        + "\n\n<b>Отменить это бронирование?</b>"
    )
    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state, text,
        reply_markup=cancel_confirm_kb(booking.id, idx),
    )


@router.callback_query(F.data.startswith("booking_cancel_confirm:"))
async def cb_booking_cancel_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await callback.answer("Некорректные данные.", show_alert=True)
        return
    booking_id = int(parts[1])

    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )

    async with SessionLocal() as session:
        try:
            await BookingService(session).cancel_booking(booking_id, user.id)
        except BookingValidationError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state,
        f"✅ Бронь #{booking_id} отменена",
        reply_markup=cancel_done_kb(),
    )


@router.callback_query(F.data.startswith("booking_cancel_back:"))
async def cb_booking_cancel_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        idx = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        idx = 0
    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )
    await _render_my_bookings(
        callback.bot, callback.message.chat.id, state, user.id, idx,
    )


# ---------------------------------------------------------------------------
# /cancel <id>
# ---------------------------------------------------------------------------

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, command: CommandObject, state: FSMContext) -> None:
    await delete_user_message(message)
    await clear_state_keep_main(state)

    if not command.args or not command.args.strip().isdigit():
        await edit_or_create_main(
            message.bot, message.chat.id, state,
            "Использование: <code>/cancel &lt;id&gt;</code>",
            reply_markup=to_home_only_kb(),
        )
        return

    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_user(tg.id, _tg_full_name(message), tg.username)
    booking_id = int(command.args.strip())

    async with SessionLocal() as session:
        try:
            await BookingService(session).cancel_booking(booking_id, user.id)
        except BookingValidationError as exc:
            await edit_or_create_main(
                message.bot, message.chat.id, state,
                f"❌ {exc}",
                reply_markup=to_home_only_kb(),
            )
            return

    await edit_or_create_main(
        message.bot, message.chat.id, state,
        f"✅ Бронь #{booking_id} отменена.",
        reply_markup=to_home_only_kb(),
    )


# ---------------------------------------------------------------------------
# Cancel button on booking-created message (callback: cancel:<id>)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("cancel:"))
async def cb_cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        booking_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    await remember_main_from_callback(state, callback.message.message_id)
    tg = callback.from_user
    user = await _ensure_user(
        tg.id, tg.full_name or tg.username or f"user_{tg.id}", tg.username,
    )

    async with SessionLocal() as session:
        try:
            await BookingService(session).cancel_booking(booking_id, user.id)
        except BookingValidationError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state,
        f"✅ Бронь #{booking_id} отменена.",
        reply_markup=to_home_only_kb(),
    )


