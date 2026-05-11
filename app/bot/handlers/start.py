from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.ui import main_menu
from app.core.config import get_settings
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.services.booking_service import RoleId

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()

    tg = message.from_user
    if tg is None:
        await message.answer("Не удалось определить Telegram-профиль.")
        return

    settings = get_settings()
    is_admin = tg.id in settings.admin_telegram_ids
    full_name = tg.full_name or tg.username or f"user_{tg.id}"

    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(tg.id)
        if user is None:
            role_id = int(RoleId.ADMIN if is_admin else RoleId.STUDENT)
            await repo.create(telegram_id=tg.id, full_name=full_name, role_id=role_id)
            await session.commit()
        elif is_admin and user.role_id != int(RoleId.ADMIN):
            user.role_id = int(RoleId.ADMIN)
            await session.commit()

    await message.answer(
        "Привет! Я помогу найти свободную аудиторию и оформить бронь.\n\n"
        "Выберите действие в меню или введите команду:\n"
        "/rooms — поиск аудиторий\n"
        "/book — создать бронь\n"
        "/my_bookings — мои брони\n"
        "/help — справка",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Как пользоваться ботом</b>\n\n"
        "/rooms — пошаговый поиск свободных аудиторий\n"
        "/book — пошаговое создание брони\n"
        "/my_bookings — список ваших активных броней\n"
        "/cancel &lt;id&gt; — отмена брони\n"
        "/start — главное меню\n\n"
        "<b>Быстрый формат</b> (одной строкой):\n"
        "<code>/book ID;начало;конец;цель</code>\n"
        "<code>/rooms начало;конец;вместимость</code>\n\n"
        "Даты: <code>2026-05-10 12:00</code> или <code>10.05.2026 12:00</code>",
    )
