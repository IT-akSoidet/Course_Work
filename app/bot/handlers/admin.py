import io

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.schedule_importer import CsvScheduleProvider, ScheduleImporter

router = Router()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in get_settings().admin_telegram_ids


async def _deny_if_not_admin(message: Message) -> bool:
    tg = message.from_user
    if tg is None or not _is_admin(tg.id):
        await message.answer("⛔ Команда доступна только администраторам.")
        return True
    return False


@router.message(Command("import_schedule"))
async def cmd_import_schedule(message: Message, command: CommandObject | None = None) -> None:
    if await _deny_if_not_admin(message):
        return

    provider: CsvScheduleProvider | None = None

    if message.document:
        buf = io.BytesIO()
        await message.bot.download(message.document, destination=buf)
        provider = CsvScheduleProvider(content=buf.getvalue())
    elif command and command.args:
        provider = CsvScheduleProvider(file_path=command.args.strip())
    else:
        await message.answer(
            "<b>📥 Импорт расписания</b>\n\n"
            "Прикрепите CSV-файл к сообщению с командой <code>/import_schedule</code>.\n\n"
            "Колонки CSV:\n"
            "<code>date,start_time,end_time,subject,subject_type,teacher,group,classroom,building</code>\n\n"
            "Строки с <code>building=online</code> или <code>classroom=online</code> пропускаются.",
        )
        return

    async with SessionLocal() as session:
        importer = ScheduleImporter(session, provider)
        try:
            report = await importer.import_schedule()
        except (ValueError, OSError) as exc:
            await message.answer(f"❌ Ошибка импорта: {exc}")
            return

    lines = [
        "✅ <b>Импорт завершён</b>",
        f"📊 Обработано строк: {report.processed_rows}",
        f"➕ Добавлено слотов: {report.inserted_slots}",
        f"⏭ Пропущено (онлайн): {report.skipped_online}",
        f"🏢 Создано корпусов: {report.created_buildings}",
        f"📍 Создано аудиторий: {report.created_rooms}",
    ]
    if report.errors:
        lines.append("")
        lines.append("⚠️ Ошибки в строках:")
        for err in report.errors[:10]:
            lines.append(f"  • {err}")
        if len(report.errors) > 10:
            lines.append(f"  • … и ещё {len(report.errors) - 10}")

    await message.answer("\n".join(lines))
