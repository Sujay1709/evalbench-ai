import json
import re
import unicodedata
from collections import Counter
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


def _normalize_qa_text(value: str) -> str:
    """Normalize free-text QA answers before token-level comparison."""

    casefolded = value.casefold()
    without_punctuation = "".join(
        character for character in casefolded if not unicodedata.category(character).startswith("P")
    )
    without_articles = re.sub(r"\b(a|an|the)\b", " ", without_punctuation)
    return re.sub(r"\s+", " ", without_articles).strip()


def _token_f1(candidate: str, expected: str) -> tuple[float, float, float]:
    candidate_tokens = _normalize_qa_text(candidate).split()
    expected_tokens = _normalize_qa_text(expected).split()

    if not candidate_tokens or not expected_tokens:
        exact_empty_match = candidate_tokens == expected_tokens
        score = 1.0 if exact_empty_match else 0.0
        return score, score, score

    common_count = sum((Counter(candidate_tokens) & Counter(expected_tokens)).values())
    if common_count == 0:
        return 0.0, 0.0, 0.0

    precision = common_count / len(candidate_tokens)
    recall = common_count / len(expected_tokens)
    f1 = 2 * precision * recall / (precision + recall)
    return f1, precision, recall


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

    if spec.type == "token_f1":
        candidate_scores = []
        for expected_answer in spec.accepted_answers:
            f1, precision, recall = _token_f1(response, expected_answer)
            candidate_scores.append(
                {
                    "expected": expected_answer,
                    "f1": f1,
                    "precision": precision,
                    "recall": recall,
                }
            )

        best_score = max(candidate_scores, key=lambda score: score["f1"])
        score = float(best_score["f1"])
        return ScoreResult(
            scorer="token_f1",
            passed=score >= spec.threshold,
            score=score,
            details={
                "threshold": spec.threshold,
                "best_expected": best_score["expected"],
                "precision": best_score["precision"],
                "recall": best_score["recall"],
                "actual": response,
            },
        )

    if spec.type == "answerability":
        normalized_response = _normalize_qa_text(response)
        normalized_abstentions = {_normalize_qa_text(phrase) for phrase in spec.abstention_phrases}
        predicted_answerable = bool(normalized_response) and (
            normalized_response not in normalized_abstentions
        )
        passed = predicted_answerable == spec.expected_answerable
        return ScoreResult(
            scorer="answerability",
            passed=passed,
            score=1.0 if passed else 0.0,
            details={
                "expected_answerable": spec.expected_answerable,
                "predicted_answerable": predicted_answerable,
                "actual": response,
            },
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
