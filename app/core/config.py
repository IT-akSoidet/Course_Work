from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = "telegram-bot-token"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/room_booking"
    redis_url: str = "redis://localhost:6379/0"
    admin_telegram_ids: List[int] = []
    app_env: str = "dev"

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | list[int] | None) -> list[int]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [int(item.strip()) for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
