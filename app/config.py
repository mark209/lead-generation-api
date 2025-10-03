from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration driven by environment variables."""

    environment: str = "development"
    cors_allowed_origins: str | None = None
    rate_limit_per_minute: int = 60
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", case_sensitive=False)

    @field_validator("rate_limit_per_minute")
    @classmethod
    def validate_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("rate_limit_per_minute must be greater than zero")
        return value

    @property
    def allowed_origins(self) -> List[str]:
        if not self.cors_allowed_origins:
            return []
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()