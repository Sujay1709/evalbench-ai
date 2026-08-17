from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "evalbench.db"


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables or `.env`."""

    app_env: Literal["development", "testing", "production"] = "development"
    secret_key: str = "development-only-secret"
    database_url: str = Field(default=f"sqlite:///{DEFAULT_DATABASE_PATH}")
    demo_read_only: bool = False
    log_level: str = "INFO"
    llm_provider: str = "mock"
    max_run_cost_usd: float = Field(default=1.0, ge=0)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.app_env == "production" and self.secret_key == "development-only-secret":
            raise ValueError("Production requires a non-default SECRET_KEY")
        return self

    def to_flask_config(self) -> dict:
        database_url = self.database_url
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        return {
            "APP_ENV": self.app_env,
            "SECRET_KEY": self.secret_key,
            "SQLALCHEMY_DATABASE_URI": database_url,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "DEMO_READ_ONLY": self.demo_read_only,
            "LOG_LEVEL": self.log_level,
            "LLM_PROVIDER": self.llm_provider,
            "MAX_RUN_COST_USD": self.max_run_cost_usd,
        }
