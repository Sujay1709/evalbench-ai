import json
import re
from dataclasses import asdict, dataclass

from jsonschema import ValidationError, validate

from evalbench.datasets import ScorerSpec


@dataclass(frozen=True)
class ScoreResult:
    scorer: str
    passed: bool
    score: float
    details: dict

    def as_dict(self) -> dict:
        return asdict(self)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def score_response(response: str, spec: ScorerSpec) -> ScoreResult:
    if spec.type == "exact_match":
        expected = spec.expected or ""
        actual_value = response.strip() if spec.case_sensitive else _normalize_text(response)
        expected_value = expected.strip() if spec.case_sensitive else _normalize_text(expected)
        passed = actual_value == expected_value
        return ScoreResult(
            scorer="exact_match",
            passed=passed,
            score=1.0 if passed else 0.0,
            details={"expected": expected, "actual": response},
        )

    try:
        parsed_response = json.loads(response)
        validate(instance=parsed_response, schema=spec.json_schema)
    except (json.JSONDecodeError, ValidationError) as exc:
        return ScoreResult(
            scorer="json_schema",
            passed=False,
            score=0.0,
            details={"error": str(exc)},
        )

    return ScoreResult(
        scorer="json_schema",
        passed=True,
        score=1.0,
        details={"parsed": parsed_response},
    )
