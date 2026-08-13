"""Application configuration, loaded from environment variables / .env file."""
from __future__ import annotations

import secrets
import warnings
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    app_name: str = "Retail Shop Manager"
    environment: str = Field(default="development")  # "development" | "production"

    # Security / auth
    secret_key: str = Field(default="")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 hours

    # Database. SQLite by default; set to a Postgres URL for cloud hosting, e.g.
    #   postgresql+psycopg://user:pass@host:5432/dbname
    database_url: str = "sqlite:///./shop.db"

    # CORS: comma-separated list of allowed frontend origins.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Optional first-run admin seeding (used only if no user exists yet).
    admin_username: str = ""
    admin_password: str = ""

    # Locale / display (frontend reads these via /api/meta)
    currency_code: str = "INR"
    currency_symbol: str = "₹"

    # Shop details printed on the receipt / bill PDF. Fill these in .env.
    shop_name: str = ""       # falls back to app_name if blank
    shop_address: str = ""    # e.g. "12 Main Road, Hyderabad - 500001"
    shop_phone: str = ""      # e.g. "+91 98765 43210"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("secret_key")
    @classmethod
    def _validate_secret(cls, v: str) -> str:
        return v.strip()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # A secret key is mandatory. In production we refuse to start without a
    # strong one. In development we generate an ephemeral one (and warn), which
    # is fine because it only invalidates tokens on restart.
    if not settings.secret_key or len(settings.secret_key) < 32:
        if settings.is_production:
            raise RuntimeError(
                "SECRET_KEY is missing or too short. Set a strong SECRET_KEY "
                "(>= 32 chars) in the environment before running in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        warnings.warn(
            "SECRET_KEY not set; generating a temporary development key. "
            "Tokens will be invalidated on restart. Set SECRET_KEY in .env.",
            stacklevel=2,
        )
        settings.secret_key = secrets.token_urlsafe(48)

    return settings
