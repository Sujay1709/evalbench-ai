from time import perf_counter

from evalbench.datasets import EvaluationExample
from evalbench.providers.base import ProviderResponse


class MockProvider:
    """Deterministic offline provider used for reproducible tests and demos."""

    name = "mock"

    def generate(self, prompt: str, example: EvaluationExample) -> ProviderResponse:
        started = perf_counter()
        output = example.mock_response
        latency_ms = (perf_counter() - started) * 1000
        return ProviderResponse(
            text=output,
            latency_ms=latency_ms,
            metadata={"offline": True, "prompt_characters": len(prompt)},
        )
