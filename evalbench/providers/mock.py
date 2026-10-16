from time import perf_counter

from evalbench.datasets import EvaluationExample
from evalbench.providers.base import ProviderResponse

MOCK_ABSTENTION = "insufficient evidence"
# Other inputs, such as a reference answer, are intentionally kept out of prompts.
ANSWER_INPUTS = ("question", "context")


class MockProvider:
    """Deterministic offline provider used for reproducible tests and demos.

    It returns the fixture answer only when the rendered prompt shows the example's
    question and context. A prompt that drops either gets an abstention, as a grounded
    model would, so prompt-template regressions are observable offline. Wording
    quality is not modeled.
    """

    name = "mock"

    def generate(self, prompt: str, example: EvaluationExample) -> ProviderResponse:
        started = perf_counter()
        hidden_inputs = [
            name
            for name in ANSWER_INPUTS
            if isinstance(value := example.input.get(name), str)
            and value.strip()
            and value not in prompt
        ]
        output = MOCK_ABSTENTION if hidden_inputs else example.mock_response
        latency_ms = (perf_counter() - started) * 1000
        metadata = {
            "offline": True,
            "prompt_characters": len(prompt),
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_basis": "offline mock; no API calls",
        }
        if hidden_inputs:
            metadata["hidden_inputs"] = hidden_inputs
        return ProviderResponse(text=output, latency_ms=latency_ms, metadata=metadata)
