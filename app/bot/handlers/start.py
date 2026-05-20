from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.single_message import (
    clear_state_keep_main,
    delete_user_message,
    edit_or_create_main,
    remember_main_from_callback,
)
from app.bot.ui import (
    HOME_MENU_TEXT,
    home_menu_inline_kb,
    to_home_only_kb,
)
from app.core.config import get_settings
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal

router = Router()


WELCOME_TEXT = (
    "👋 Привет! Я помогу найти свободную аудиторию ВШЭ НН.\n\n"
    "Выберите действие:"
)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_settings().admin_telegram_ids


def _tg_full_name(message: Message) -> str:
    tg = message.from_user
    if tg is None:
        return "user"
    return tg.full_name or tg.username or f"user_{tg.id}"


def _help_text(is_admin: bool) -> str:
    extra = (
        "\n• /import_schedule — импорт CSV-расписания (с прикреплённым файлом)"
        if is_admin else ""
    )
    return (
        "<b>Как пользоваться ботом</b>\n\n"
        "• /book — создать бронирование (дата → аудитория → время → цель)\n"
        "• /my_bookings — список ваших активных броней\n"
        "• /cancel &lt;id&gt; — отменить бронь по номеру\n"
        "• /start — главное меню" + extra
    )


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await delete_user_message(message)
    await state.clear()

    tg = message.from_user
    if tg is None:
        await message.answer("Не удалось определить Telegram-профиль.")
        return

    async with SessionLocal() as session:
        repo = UserRepository(session)
        await repo.upsert(
            telegram_id=tg.id,
            full_name=_tg_full_name(message),
            username=tg.username,
        )
        await session.commit()

    await edit_or_create_main(
        message.bot, message.chat.id, state,
        WELCOME_TEXT,
        reply_markup=home_menu_inline_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await delete_user_message(message)
    await clear_state_keep_main(state)

    tg = message.from_user
    is_admin = bool(tg and _is_admin(tg.id))
    await edit_or_create_main(
        message.bot, message.chat.id, state,
        _help_text(is_admin),
        reply_markup=to_home_only_kb(),
    )


# ---------------------------------------------------------------------------
# Navigation callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "act:home")
async def cb_act_home(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_state_keep_main(state)
    await remember_main_from_callback(state, callback.message.message_id)
    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state,
        HOME_MENU_TEXT,
        reply_markup=home_menu_inline_kb(),
    )


@router.callback_query(F.data == "act:help")
async def cb_act_help(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_state_keep_main(state)
    await remember_main_from_callback(state, callback.message.message_id)
    is_admin = _is_admin(callback.from_user.id)
    await edit_or_create_main(
        callback.bot, callback.message.chat.id, state,
        _help_text(is_admin),
        reply_markup=to_home_only_kb(),
    )
