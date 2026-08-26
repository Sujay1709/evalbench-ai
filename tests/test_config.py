import pytest
from pydantic import ValidationError

from evalbench.config import Settings


def test_openai_provider_requires_an_api_key():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, llm_provider="openai", openai_api_key=None)


def test_openai_secret_is_not_copied_into_flask_config():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key="test-secret",
    )

    flask_config = settings.to_flask_config()

    assert flask_config["LLM_PROVIDER"] == "openai"
    assert flask_config["OPENAI_MODEL"] == "gpt-5.6-luna"
    assert "OPENAI_API_KEY" not in flask_config


def test_full_production_mode_requires_an_inngest_signing_key():
    with pytest.raises(ValidationError, match="INNGEST_SIGNING_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="production-secret",
            demo_read_only=False,
            inngest_signing_key=None,
        )


def test_read_only_production_demo_does_not_require_inngest_keys():
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="production-secret",
        demo_read_only=True,
        inngest_event_key=None,
        inngest_signing_key=None,
    )

    assert settings.demo_read_only is True


def test_inngest_secrets_are_not_copied_into_flask_config():
    settings = Settings(
        _env_file=None,
        inngest_event_key="event-secret",
        inngest_signing_key="signing-secret",
    )

    flask_config = settings.to_flask_config()

    assert flask_config["INNGEST_APP_ID"] == "evalbench"
    assert "INNGEST_EVENT_KEY" not in flask_config
    assert "INNGEST_SIGNING_KEY" not in flask_config
