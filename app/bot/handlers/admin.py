import io

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.bot.parsers import format_dt, format_time
from app.bot.ui import admin_decision_kb
from app.core.config import get_settings
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter
from app.services.booking_service import BookingValidationError, RoleId
from app.services.moderation_service import ModerationService

router = Router()


async def _ensure_admin(telegram_id: int, full_name: str):
    settings = get_settings()
    async with SessionLocal() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(telegram_id)
        if user is None and telegram_id in settings.admin_telegram_ids:
            user = await repo.create(
                telegram_id=telegram_id, full_name=full_name, role_id=int(RoleId.ADMIN),
            )
            await session.commit()
        elif user is not None and telegram_id in settings.admin_telegram_ids and user.role_id != int(RoleId.ADMIN):
            user.role_id = int(RoleId.ADMIN)
            await session.commit()
        return user


def _check_admin(user) -> bool:
    return user is not None and user.role_id == int(RoleId.ADMIN)


# ---------------------------------------------------------------------------
# /admin_queue
# ---------------------------------------------------------------------------

@router.message(Command("admin_queue"))
@router.message(F.text == "Модерация")
async def cmd_admin_queue(message: Message) -> None:
    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        await message.answer("Команда доступна только администраторам.")
        return

    async with SessionLocal() as session:
        pending = await ModerationService(session).list_pending()

    if not pending:
        await message.answer("Очередь модерации пуста.")
        return

    for item in pending[:20]:
        await message.answer(
            f"<b>Заявка #{item.id}</b>\n"
            f"Пользователь: {item.user_id}\n"
            f"Аудитория: <code>{item.room_id}</code>\n"
            f"Время: {format_dt(item.starts_at)} — {format_time(item.ends_at)}",
            reply_markup=admin_decision_kb(item.id),
        )


# ---------------------------------------------------------------------------
# /approve, /reject (text commands)
# ---------------------------------------------------------------------------

@router.message(Command("approve"))
async def cmd_approve(message: Message, command: CommandObject) -> None:
    await _handle_text_decision(message, command, is_approve=True)


@router.message(Command("reject"))
async def cmd_reject(message: Message, command: CommandObject) -> None:
    await _handle_text_decision(message, command, is_approve=False)


async def _handle_text_decision(message: Message, command: CommandObject, is_approve: bool) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Использование: /approve &lt;id&gt; или /reject &lt;id&gt;")
        return

    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        await message.answer("Команда доступна только администраторам.")
        return

    booking_id = int(command.args.strip())
    async with SessionLocal() as session:
        service = ModerationService(session)
        try:
            b = await (service.approve(booking_id, user.id) if is_approve else service.reject(booking_id, user.id))
        except BookingValidationError as exc:
            await message.answer(f"Ошибка: {exc}")
            return
    label = "подтверждена" if is_approve else "отклонена"
    await message.answer(f"Заявка #{b.id} {label}.")


# ---------------------------------------------------------------------------
# Callback: admin decision buttons
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("adm:"))
async def cb_admin_decision(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer("Сообщение недоступно.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    action, raw_id = parts[1], parts[2]
    if action not in {"ok", "no"} or not raw_id.isdigit():
        await callback.answer("Некорректный формат.", show_alert=True)
        return

    user = await _ensure_admin(callback.from_user.id, callback.from_user.full_name)
    if not _check_admin(user):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    booking_id = int(raw_id)
    async with SessionLocal() as session:
        service = ModerationService(session)
        try:
            if action == "ok":
                await service.approve(booking_id, user.id)
                text = f"Заявка #{booking_id} подтверждена."
            else:
                await service.reject(booking_id, user.id)
                text = f"Заявка #{booking_id} отклонена."
        except BookingValidationError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(text)
    await callback.answer()


# ---------------------------------------------------------------------------
# /import_schedule  —  attach CSV file or specify server path
# ---------------------------------------------------------------------------

@router.message(Command("import_schedule"))
async def cmd_import_schedule(message: Message, command: CommandObject | None = None) -> None:
    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        await message.answer("Команда доступна только администраторам.")
        return

    provider: CsvScheduleProvider | None = None

    if message.document:
        buf = io.BytesIO()
        await message.bot.download(message.document, destination=buf)
        provider = CsvScheduleProvider(content=buf.getvalue())

    elif command and command.args:
        csv_path = command.args.strip()
        provider = CsvScheduleProvider(file_path=csv_path)

    else:
        await message.answer(
            "<b>Импорт расписания</b>\n\n"
            "Прикрепите CSV-файл к сообщению с командой /import_schedule\n"
            "или укажите путь: <code>/import_schedule data/university_schedule.csv</code>\n\n"
            "Колонки CSV: <code>room_id, starts_at, ends_at, external_id, comment</code>",
        )
        return

    async with SessionLocal() as session:
        importer = ScheduleImporter(session, provider)
        try:
            count = await importer.import_schedule()
        except (ValueError, OSError) as exc:
            await message.answer(f"Ошибка импорта: {exc}")
            return

    await message.answer(f"Импорт завершён. Загружено слотов: {count}")
