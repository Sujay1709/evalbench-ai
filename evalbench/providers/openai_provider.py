from time import perf_counter
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, OpenAIError

from evalbench.datasets import EvaluationExample
from evalbench.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderResponse,
    ProviderResponseError,
    ProviderTransientError,
)


class OpenAIProvider:
    """Opt-in Responses API adapter with bounded retries and safe metadata."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_output_tokens: int = 128,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise ProviderConfigurationError("OPENAI_API_KEY is required for the OpenAI provider")
        if not model.strip():
            raise ProviderConfigurationError("OPENAI_MODEL is required for the OpenAI provider")
        if max_output_tokens < 16:
            raise ProviderConfigurationError("OPENAI_MAX_OUTPUT_TOKENS must be at least 16")

        self.model = model
        self.max_output_tokens = max_output_tokens
        self.name = f"openai:{model}:max{max_output_tokens}"
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def generate(self, prompt: str, example: EvaluationExample) -> ProviderResponse:
        del example  # The rendered prompt is the only data sent to the provider.
        started = perf_counter()

        try:
            response = self._client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise ProviderTransientError(f"OpenAI connection failed: {exc}") from exc
        except APIStatusError as exc:
            if exc.status_code == 429 or exc.status_code >= 500:
                raise ProviderTransientError(
                    f"OpenAI temporarily failed with HTTP {exc.status_code}"
                ) from exc
            raise ProviderError(f"OpenAI request failed with HTTP {exc.status_code}") from exc
        except OpenAIError as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc

        output_text = (getattr(response, "output_text", "") or "").strip()
        if not output_text:
            raise ProviderResponseError("OpenAI returned no text output")

        usage = getattr(response, "usage", None)
        metadata = {
            "response_id": response.id,
            "model": response.model,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "stored": False,
        }
        return ProviderResponse(
            text=output_text,
            latency_ms=(perf_counter() - started) * 1000,
            metadata=metadata,
        )
