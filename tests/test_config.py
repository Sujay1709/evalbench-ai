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
