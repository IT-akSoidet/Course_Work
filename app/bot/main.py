import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import admin, booking, start
from app.core.config import get_settings
from app.core.logging import configure_logging


async def run_bot() -> None:
    settings = get_settings()
    configure_logging()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
