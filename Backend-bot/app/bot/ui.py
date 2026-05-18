from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_admin: bool = False, webapp_url: str = "") -> ReplyKeyboardMarkup:
    rows = []

    # Кнопка открытия Mini App (если URL настроен)
    if webapp_url:
        rows.append([KeyboardButton(text="📅 Забронировать аудиторию", web_app=WebAppInfo(url=webapp_url))])

    rows.append([KeyboardButton(text="Найти аудитории"), KeyboardButton(text="Мои брони")])
    rows.append([KeyboardButton(text="Помощь")])

    if is_admin:
        rows.append([KeyboardButton(text="Модерация")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="flow:cancel")]]
    )


def booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отменить бронь", callback_data=f"bk:cancel:{booking_id}")]
        ]
    )


def admin_decision_kb(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить", callback_data=f"adm:ok:{booking_id}")
    builder.button(text="Отклонить", callback_data=f"adm:no:{booking_id}")
    builder.adjust(2)
    return builder.as_markup()


def format_room_list(rooms) -> str:
    grouped: dict[tuple, list] = {}
    for room in rooms:
        bld = room.building
        key = (bld.id, bld.name, bld.address)
        grouped.setdefault(key, []).append(room)

    lines: list[str] = []
    for (_, name, address), building_rooms in grouped.items():
        lines.append(f"<b>{name}</b> ({address}):")
        for r in building_rooms:
            lines.append(f"  <code>{r.id}</code> — ауд. {r.name}, {r.capacity} мест")
    return "\n".join(lines)
