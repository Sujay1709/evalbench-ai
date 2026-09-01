import math
from collections.abc import Iterable
from dataclasses import dataclass


class AggregationError(ValueError):
    """Persisted example scores cannot produce trustworthy run metrics."""


@dataclass(frozen=True)
class AggregateMetrics:
    passed_examples: int
    mean_score: float
    total_examples: int


def aggregate_example_scores(results: Iterable[tuple[bool, float]]) -> AggregateMetrics:
    """Calculate deterministic run metrics from validated example outcomes."""

    outcomes = tuple(results)
    if not outcomes:
        raise AggregationError("Cannot aggregate a run without example results")

    for _, score in outcomes:
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise AggregationError(f"Example score must be finite and between 0 and 1; got {score}")

    return AggregateMetrics(
        passed_examples=sum(passed for passed, _ in outcomes),
        mean_score=sum(score for _, score in outcomes) / len(outcomes),
        total_examples=len(outcomes),
    )
