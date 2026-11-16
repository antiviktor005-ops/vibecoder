from decimal import Decimal
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    bot_token: SecretStr
    admin_telegram_id: int = Field(gt=0)
    allowed_user_ids: str = ""  # Compatibility only. Access is always admin-only.
    database_url: SecretStr
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    app_env: str = "production"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    search_interval_minutes: int = Field(default=30, ge=1, le=1440)
    ai_daily_request_limit: int = Field(default=20, ge=0)
    ai_daily_budget_usd: Decimal = Field(default=Decimal("1"), ge=0)
    ai_daily_token_limit: int = Field(default=50000, ge=0)
    ai_input_usd_per_million: Decimal = Field(default=Decimal("0.15"), gt=0)
    ai_output_usd_per_million: Decimal = Field(default=Decimal("0.60"), gt=0)


def pg_url(value: str) -> URL:
    url = make_url(value)
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
        raise ValueError("Требуется PostgreSQL.")
    if "sslmode" in url.query:
        ssl = url.query["sslmode"]
        url = url.difference_update_query(["sslmode"]).update_query_dict({"ssl": ssl})
    return url.set(drivername="postgresql+asyncpg")
