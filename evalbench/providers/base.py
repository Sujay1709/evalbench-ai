from dataclasses import dataclass, field
from typing import Protocol

from evalbench.datasets import EvaluationExample


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    latency_ms: float
    metadata: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str

    def generate(self, prompt: str, example: EvaluationExample) -> ProviderResponse: ...
