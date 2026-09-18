from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    )

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
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
        if self.app_env == "production" and not self.demo_read_only and (
            self.inngest_signing_key is None
            or not self.inngest_signing_key.get_secret_value().strip()
        ):
            raise ValueError("Full production mode requires INNGEST_SIGNING_KEY")
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
            "OPENAI_MODEL": self.openai_model,
            "INNGEST_APP_ID": self.inngest_app_id,
        }
