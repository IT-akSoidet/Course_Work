import io
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from app.bot.parsers import format_dt, format_time
from app.bot.ui import admin_decision_kb
from app.core.config import get_settings
from app.db.repositories.user_repo import UserRepository
from app.db.session import SessionLocal
from app.integrations.public_schedule_sync import (
    sync_public_schedule,
    sync_public_schedule_with_room_autofill,
)
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter
from app.services.booking_service import BookingValidationError, RoleId
from app.services.moderation_service import ModerationService

router = Router()
sync_waiting_users: set[int] = set()


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


def _is_google_sheet_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc.endswith("docs.google.com") and "/spreadsheets/d/" in parsed.path


def _parse_sync_args(raw_args: str | None) -> tuple[str | None, list[str]]:
    if not raw_args:
        return None, []
    index_url: str | None = None
    sheet_urls: list[str] = []
    for token in raw_args.split():
        value = token.strip()
        if not value:
            continue
        if _is_google_sheet_url(value):
            sheet_urls.append(value)
        elif index_url is None:
            index_url = value
    return index_url, sheet_urls


async def _run_sync(
    message: Message,
    *,
    index_url: str | None,
    sheet_urls: list[str],
) -> None:
    await message.answer("Запускаю синхронизацию расписания из публичных таблиц...")
    async with SessionLocal() as session:
        try:
            result = await sync_public_schedule(
                session,
                index_url=index_url,
                sheet_urls=sheet_urls,
                source="hse_public_sheets",
                replace_source=True,
            )
        except (ValueError, OSError) as exc:
            await message.answer(f"Ошибка синхронизации: {exc}")
            return

    await message.answer(
        "<b>Синхронизация завершена</b>\n"
        f"Таблиц обработано: {result.sheet_urls_total}\n"
        f"Слотов загружено: {result.imported_slots}\n"
        f"Строк обработано: {result.rows_processed}\n"
        f"Пропущено (online/пусто): {result.rows_skipped_online_or_empty}\n"
        f"Пропущено (не найдена аудитория в БД): {result.rows_skipped_unknown_room}"
    )


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


@router.message(Command("sync_schedule"))
async def cmd_sync_schedule(message: Message, command: CommandObject | None = None) -> None:
    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        await message.answer("Команда доступна только администраторам.")
        return

    settings = get_settings()
    arg_index_url, arg_sheet_urls = _parse_sync_args(command.args if command else None)
    index_url = arg_index_url or settings.schedule_index_url
    sheet_urls = arg_sheet_urls or settings.schedule_sheet_urls

    if not index_url and not sheet_urls:
        sync_waiting_users.add(tg.id)
        await message.answer(
            "<b>Синхронизация расписания</b>\n\n"
            "Укажите ссылку на главную страницу или прямые Google Sheets URL:\n"
            "<code>/sync_schedule https://docs.360.yandex.ru/... </code>\n"
            "<code>/sync_schedule https://docs.google.com/spreadsheets/d/.../edit?gid=...</code>\n\n"
            "Также можно задать в .env: <code>SCHEDULE_INDEX_URL</code> и "
            "<code>SCHEDULE_SHEET_URLS</code>.\n\n"
            "Можно отправить ссылку отдельным следующим сообщением."
        )
        return

    sync_waiting_users.discard(tg.id)
    await _run_sync(message, index_url=index_url, sheet_urls=sheet_urls)


@router.message(F.text)
async def catch_sync_url_after_command(message: Message) -> None:
    tg = message.from_user
    if tg is None or tg.id not in sync_waiting_users:
        return

    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        sync_waiting_users.discard(tg.id)
        return

    index_url, sheet_urls = _parse_sync_args(message.text)
    if not index_url and not sheet_urls:
        await message.answer(
            "Не вижу валидной ссылки. Пришлите URL на docs.360.yandex.ru или docs.google.com/spreadsheets/..."
        )
        return

    sync_waiting_users.discard(tg.id)
    await _run_sync(message, index_url=index_url, sheet_urls=sheet_urls)


@router.message(Command("sync_schedule_autofill"))
async def cmd_sync_schedule_autofill(message: Message, command: CommandObject | None = None) -> None:
    tg = message.from_user
    if tg is None:
        return
    user = await _ensure_admin(tg.id, tg.full_name)
    if not _check_admin(user):
        await message.answer("Команда доступна только администраторам.")
        return

    settings = get_settings()
    arg_index_url, arg_sheet_urls = _parse_sync_args(command.args if command else None)
    index_url = arg_index_url or settings.schedule_index_url
    sheet_urls = arg_sheet_urls or settings.schedule_sheet_urls

    if not index_url and not sheet_urls:
        await message.answer(
            "Укажите ссылку: <code>/sync_schedule_autofill https://docs.google.com/spreadsheets/d/.../edit?gid=...</code>"
        )
        return

    await message.answer("Ищу недостающие аудитории, добавляю их в rooms и запускаю синхронизацию...")
    async with SessionLocal() as session:
        try:
            result = await sync_public_schedule_with_room_autofill(
                session=session,
                index_url=index_url,
                sheet_urls=sheet_urls,
                default_capacity=40,
                source="hse_public_sheets",
            )
        except (ValueError, OSError) as exc:
            await message.answer(f"Ошибка автозаполнения: {exc}")
            return

    sync = result.sync_result
    await message.answer(
        "<b>Автозаполнение + синхронизация завершены</b>\n"
        f"Недостающих пар найдено: {result.missing_pairs_detected}\n"
        f"Добавлено корпусов: {result.created_buildings}\n"
        f"Добавлено аудиторий: {result.created_rooms}\n\n"
        f"Таблиц обработано: {sync.sheet_urls_total}\n"
        f"Слотов загружено: {sync.imported_slots}\n"
        f"Строк обработано: {sync.rows_processed}\n"
        f"Пропущено (online/пусто): {sync.rows_skipped_online_or_empty}\n"
        f"Пропущено (не найдена аудитория в БД): {sync.rows_skipped_unknown_room}"
    )
