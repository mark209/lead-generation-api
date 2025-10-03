import json
from functools import lru_cache
from typing import Any, List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration driven by environment variables."""

    environment: str = "development"
    cors_allowed_origins: str | None = None
    rate_limit_per_minute: int = 60
    log_level: str = "INFO"
    google_service_account_json: str | None = None
    google_sheet_id: str | None = None
    google_sheet_worksheet: str | None = None

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

    @property
    def google_sheets_enabled(self) -> bool:
        return bool(self.google_sheet_id and self.google_service_account_json)

    @property
    def google_service_account_info(self) -> dict[str, Any]:
        if not self.google_service_account_json:
            raise ValueError("google_service_account_json is not configured")
        try:
            return json.loads(self.google_service_account_json)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError("google_service_account_json is not valid JSON") from exc


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()