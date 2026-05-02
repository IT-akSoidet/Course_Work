from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я бот бронирования аудиторий.\n"
        "Команды:\n"
        "/book - создать бронь\n"
        "/my_bookings - мои брони\n"
        "/admin_queue - очередь модерации (админ)\n"
    )
