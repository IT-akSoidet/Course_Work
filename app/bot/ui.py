from datetime import datetime, timedelta

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.parsers import format_date_btn, format_time
from app.core.config import MOSCOW_TZ
from app.services.free_slots import FreeWindow, format_windows


HOME_MENU_TEXT = "Выберите действие:"


# ---------------------------------------------------------------------------
# Inline navigation menu
# ---------------------------------------------------------------------------

def home_menu_inline_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Новая бронь", callback_data="act:book")
    builder.button(text="📋 Мои брони", callback_data="act:my")
    builder.button(text="ℹ️ Помощь", callback_data="act:help")
    builder.adjust(1, 2)
    return builder.as_markup()


def to_home_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="act:home")]
        ]
    )


# ---------------------------------------------------------------------------
# Booking flow keyboards
# ---------------------------------------------------------------------------

def date_picker_kb(prefix: str, days: int = 7) -> InlineKeyboardMarkup:
    today = datetime.now(tz=MOSCOW_TZ).date()
    builder = InlineKeyboardBuilder()
    for i in range(days):
        d = today + timedelta(days=i)
        builder.button(
            text=format_date_btn(d, today),
            callback_data=f"{prefix}:date:{d.isoformat()}",
        )
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()


def back_cancel_kb(prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=f"{prefix}:back")
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(2)
    return builder.as_markup()


def _short_building(name: str) -> str:
    short = name.removeprefix("Корпус ").strip()
    return short or name


def rooms_list_kb(rooms: list, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for room in rooms:
        builder.button(
            text=f"Ауд. {room.name}, {_short_building(room.building.name)}",
            callback_data=f"{prefix}:room:{room.id}",
        )
    builder.button(text="🔙 Назад", callback_data=f"{prefix}:back")
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    room_rows = [2] * (len(rooms) // 2)
    if len(rooms) % 2 == 1:
        room_rows.append(1)
    builder.adjust(*room_rows, 2)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Booking summary / cards
# ---------------------------------------------------------------------------

def format_free_summary(
    rooms_with_windows: list[tuple[object, list[FreeWindow]]],
    header: str,
) -> str:
    if not rooms_with_windows:
        return f"{header}\n\nСвободных аудиторий нет."

    grouped: dict[tuple[int, str], list[tuple[object, list[FreeWindow]]]] = {}
    for room, windows in rooms_with_windows:
        key = (room.building.id, room.building.name)
        grouped.setdefault(key, []).append((room, windows))

    lines = [header, ""]
    for (_, building_name), items in grouped.items():
        lines.append(f"🏢 <b>{building_name}</b>")
        for room, windows in items:
            lines.append(
                f"📍 Ауд. {room.name} ({room.capacity} мест) — "
                f"свободно: {format_windows(windows)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def format_booking_card(booking) -> str:
    room = booking.room
    building = room.building
    starts = booking.starts_at
    ends = booking.ends_at
    if starts.tzinfo is not None:
        starts = starts.astimezone(MOSCOW_TZ)
    if ends.tzinfo is not None:
        ends = ends.astimezone(MOSCOW_TZ)

    return (
        f"📍 Ауд. {room.name}, {building.name}\n"
        f"📅 {starts.strftime('%d.%m.%Y')}, "
        f"{format_time(booking.starts_at)}–{format_time(booking.ends_at)}\n"
        f"📝 {booking.purpose or '—'}\n"
        f"🆔 Бронь #{booking.id}"
    )


# ---------------------------------------------------------------------------
# Booking-created and /my_bookings keyboards
# ---------------------------------------------------------------------------

def booking_created_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить бронь", callback_data=f"cancel:{booking_id}")
    builder.button(text="🏠 В главное меню", callback_data="act:home")
    builder.adjust(2)
    return builder.as_markup()


def my_bookings_kb(booking_id: int, idx: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if total > 1:
        prev_idx = (idx - 1) % total
        next_idx = (idx + 1) % total
        builder.button(text="◀️ Пред.", callback_data=f"booking_page:{prev_idx}")
        builder.button(text="▶️ След.", callback_data=f"booking_page:{next_idx}")
    builder.button(
        text="❌ Отменить эту бронь",
        callback_data=f"booking_cancel:{booking_id}:{idx}",
    )
    builder.button(text="🏠 В главное меню", callback_data="act:home")
    if total > 1:
        builder.adjust(2, 1, 1)
    else:
        builder.adjust(1, 1)
    return builder.as_markup()


def cancel_confirm_kb(booking_id: int, idx: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, отменить",
        callback_data=f"booking_cancel_confirm:{booking_id}:{idx}",
    )
    builder.button(text="◀️ Назад", callback_data=f"booking_cancel_back:{idx}")
    builder.adjust(2)
    return builder.as_markup()


def cancel_done_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Остальные брони", callback_data="act:my")
    builder.button(text="🏠 В главное меню", callback_data="act:home")
    builder.adjust(2)
    return builder.as_markup()


def empty_bookings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Создать бронь", callback_data="act:book")
    builder.button(text="🏠 В главное меню", callback_data="act:home")
    builder.adjust(2)
    return builder.as_markup()
