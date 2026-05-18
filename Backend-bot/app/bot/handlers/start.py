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
        f"Привет, {full_name}! 👋\n\n"
        "Я помогу найти свободную аудиторию в НИУ ВШЭ — Нижний Новгород "
        "и оформить бронирование.\n\n"
        "Нажмите кнопку ниже, чтобы открыть приложение, "
        "или используйте команды:\n"
        "/rooms — поиск аудиторий\n"
        "/my_bookings — мои бронирования\n"
        "/help — справка",
        reply_markup=main_menu(is_admin=is_admin, webapp_url=settings.webapp_url),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Как пользоваться ботом</b>\n\n"
        "📅 <b>Открыть приложение</b> — кнопка в меню или /start\n"
        "/rooms — пошаговый поиск свободных аудиторий\n"
        "/my_bookings — список ваших активных бронирований\n"
        "/help — эта справка\n\n"
        "<b>Алгоритм бронирования:</b>\n"
        "1. Выберите дату\n"
        "2. Выберите корпус\n"
        "3. Укажите время (начало и конец)\n"
        "4. Выберите свободную аудиторию\n"
        "5. Подтвердите бронирование\n\n"
        "Бронирование действует пока не истечёт или вы не отмените его.",
    )
