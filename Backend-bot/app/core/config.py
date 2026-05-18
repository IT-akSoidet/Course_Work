from functools import lru_cache
from typing import List, Optional
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = "telegram-bot-token"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/room_booking"
    redis_url: str = "redis://localhost:6379/0"
    webapp_url: str = ""
    telegram_proxy_url: Optional[str] = None
    telegram_connect_retries: int = 10
    telegram_retry_delay_seconds: int = 3
    telegram_retry_max_delay_seconds: int = 30
    telegram_request_timeout_seconds: int = 60
    admin_telegram_ids: List[int] = []
    app_env: str = "dev"
    schedule_index_url: Optional[str] = None
    schedule_sheet_urls: List[str] = []
    schedule_sync_interval_hours: int = 0

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | int | list[int] | None) -> list[int]:
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return value
        return [int(item.strip()) for item in value.split(",") if item.strip()]

    @field_validator("telegram_proxy_url", mode="before")
    @classmethod
    def empty_proxy_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("schedule_sheet_urls", mode="before")
    @classmethod
    def parse_schedule_sheet_urls(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
