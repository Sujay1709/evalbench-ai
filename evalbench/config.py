from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from evalbench.database import database_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "evalbench.db"


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables or `.env`."""

    app_env: Literal["development", "testing", "production"] = "development"
    secret_key: str = "development-only-secret"
    database_url: SecretStr = Field(default=SecretStr(f"sqlite:///{DEFAULT_DATABASE_PATH}"))
    database_ssl_root_cert: Path | None = None
    database_pool_size: int = Field(default=3, ge=1, le=20)
    database_max_overflow: int = Field(default=2, ge=0, le=20)
    database_pool_timeout_seconds: int = Field(default=30, ge=1, le=120)
    database_pool_recycle_seconds: int = Field(default=300, ge=30, le=3600)
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    demo_read_only: bool = False
    log_level: str = "INFO"
    llm_provider: Literal["mock", "openai"] = "mock"
    max_run_cost_usd: float = Field(default=1.0, ge=0)
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=10)
    openai_max_output_tokens: int = Field(default=128, ge=16, le=4096)
    openai_input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    openai_output_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    inngest_app_id: str = Field(default="evalbench", min_length=1, max_length=64)
    inngest_event_key: SecretStr | None = None
    inngest_signing_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        self.database_flask_config()
        if (self.openai_input_usd_per_million is None) != (
            self.openai_output_usd_per_million is None
        ):
            raise ValueError("Configure both OpenAI input and output prices, or neither")
        if self.app_env == "production" and self.secret_key == "development-only-secret":
            raise ValueError("Production requires a non-default SECRET_KEY")
        if self.llm_provider == "openai" and (
            self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()
        ):
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        if (
            self.app_env == "production"
            and not self.demo_read_only
            and (
                self.inngest_signing_key is None
                or not self.inngest_signing_key.get_secret_value().strip()
            )
        ):
            raise ValueError("Full production mode requires INNGEST_SIGNING_KEY")
        return self

    def database_flask_config(self) -> dict:
        return database_config(
            self.database_url.get_secret_value(),
            production=self.app_env == "production",
            ssl_root_cert=self.database_ssl_root_cert,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout=self.database_pool_timeout_seconds,
            pool_recycle=self.database_pool_recycle_seconds,
            connect_timeout=self.database_connect_timeout_seconds,
        )

    def to_flask_config(self) -> dict:
        return {
            **self.database_flask_config(),
            "APP_ENV": self.app_env,
            "SECRET_KEY": self.secret_key,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "DEMO_READ_ONLY": self.demo_read_only,
            "LOG_LEVEL": self.log_level,
            "LLM_PROVIDER": self.llm_provider,
            "MAX_RUN_COST_USD": self.max_run_cost_usd,
            "OPENAI_MODEL": self.openai_model,
            "INNGEST_APP_ID": self.inngest_app_id,
        }
