import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand

from app.bot.handlers import admin, booking, start
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.seed import seed_reference_data
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="rooms", description="Поиск свободных аудиторий"),
    BotCommand(command="book", description="Создать бронь"),
    BotCommand(command="my_bookings", description="Мои бронирования"),
    BotCommand(command="help", description="Справка"),
]


def _resolve_proxy_url(settings_proxy: str | None) -> str | None:
    if settings_proxy:
        return settings_proxy
    return os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or os.getenv("ALL_PROXY")


def _build_session(settings) -> AiohttpSession:
    proxy_url = _resolve_proxy_url(settings.telegram_proxy_url)
    kwargs: dict = {"timeout": float(settings.telegram_request_timeout_seconds)}
    if proxy_url:
        kwargs["proxy"] = proxy_url
        logger.info("Using proxy for Telegram API: %s", proxy_url)
    else:
        logger.info("Connecting to Telegram API directly (no proxy).")
    return AiohttpSession(**kwargs)


async def _set_commands_with_retry(
    bot: Bot,
    retries: int,
    delay_seconds: int,
    max_delay_seconds: int,
) -> None:
    delay = max(1, delay_seconds)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            await bot.set_my_commands(BOT_COMMANDS)
            logger.info("Bot commands configured.")
            return
        except TelegramNetworkError as exc:
            last_exc = exc
            if attempt >= retries:
                break
            logger.warning(
                "Telegram API unavailable (attempt %s/%s): %s. Retry in %s s.",
                attempt,
                retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max(1, max_delay_seconds))
    logger.error(
        "Cannot reach Telegram API after %s attempts. "
        "Check VPN/proxy (TELEGRAM_PROXY_URL) and try again. Last error: %s",
        retries,
        last_exc,
    )
    raise last_exc if last_exc else RuntimeError("Telegram API unreachable")


async def run_bot() -> None:
    settings = get_settings()
    configure_logging()

    async with SessionLocal() as session:
        try:
            await seed_reference_data(session)
            await session.commit()
            logger.info("Reference data seeded.")
        except Exception:
            await session.rollback()
            logger.warning("Seed skipped (tables may not exist yet — run alembic upgrade head).")

    aiohttp_session = _build_session(settings)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=aiohttp_session,
    )

    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    try:
        await _set_commands_with_retry(
            bot=bot,
            retries=max(1, settings.telegram_connect_retries),
            delay_seconds=settings.telegram_retry_delay_seconds,
            max_delay_seconds=settings.telegram_retry_max_delay_seconds,
        )

        logger.info("Bot starting polling...")
        while True:
            try:
                await dp.start_polling(bot)
                break
            except TelegramNetworkError as exc:
                logger.warning(
                    "Polling interrupted by network error: %s. Restart in %s s.",
                    exc,
                    settings.telegram_retry_delay_seconds,
                )
                await asyncio.sleep(max(1, settings.telegram_retry_delay_seconds))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
