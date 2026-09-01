from dataclasses import dataclass

from jsonschema import SchemaError

from evalbench.datasets import EvaluationExample
from evalbench.scorers import score_response


@dataclass(frozen=True)
class ScoredExample:
    passed: bool
    score: float
    scorer_details: list[dict]


class DeterministicScoringError(ValueError):
    """A deterministic scorer is configured in a way that cannot be evaluated."""


def score_example_output(output_text: str, example: EvaluationExample) -> ScoredExample:
    """Apply every configured deterministic scorer to one generated output."""

    try:
        scores = [score_response(output_text, spec) for spec in example.scorers]
    except SchemaError as exc:
        raise DeterministicScoringError(
            f"Example '{example.id}' contains an invalid JSON Schema scorer"
        ) from exc
    return ScoredExample(
        passed=all(score.passed for score in scores),
        score=sum(score.score for score in scores) / len(scores),
        scorer_details=[score.as_dict() for score in scores],
    )
