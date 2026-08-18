from evalbench.config import Settings
from evalbench.providers.base import Provider
from evalbench.providers.mock import MockProvider
from evalbench.providers.openai_provider import OpenAIProvider


def build_provider(settings: Settings) -> Provider:
    """Build the configured system under test without exposing its secret."""

    if settings.llm_provider == "mock":
        return MockProvider()

    api_key = settings.openai_api_key
    if api_key is None:  # Settings validation normally catches this first.
        raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")

    return OpenAIProvider(
        api_key=api_key.get_secret_value(),
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        max_output_tokens=settings.openai_max_output_tokens,
    )
