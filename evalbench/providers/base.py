from dataclasses import dataclass, field
from typing import Protocol

from evalbench.datasets import EvaluationExample


class ProviderError(RuntimeError):
    """Base error for provider failures with a safe, actionable message."""


class ProviderConfigurationError(ProviderError):
    """The provider cannot start because required configuration is missing."""


class ProviderTransientError(ProviderError):
    """A temporary provider failure that may succeed when retried later."""


class ProviderResponseError(ProviderError):
    """The provider returned a response that EvalBench cannot evaluate."""


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    latency_ms: float
    metadata: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def generate(self, prompt: str, example: EvaluationExample) -> ProviderResponse: ...
