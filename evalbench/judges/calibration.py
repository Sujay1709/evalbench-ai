"""Pair explicitly selected human and judge ratings for calibration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evalbench.judges.rubrics import RubricDefinition
    from evalbench.models import HumanLabelSet, JudgeAttempt


class CalibrationError(ValueError):
    """Selected ratings cannot be compared safely."""


@dataclass(frozen=True)
class CriterionPair:
    criterion_id: str
    human_score: int
    judge_score: int


@dataclass(frozen=True)
class CalibrationPair:
    result_id: int
    human_label_id: str
    judge_attempt_id: str
    rubric_hash: str
    criteria: tuple[CriterionPair, ...]


def _scores_by_criterion(
    rows: object,
    *,
    expected_ids: tuple[str, ...],
    source: str,
) -> dict[str, int]:
    if not isinstance(rows, (list, tuple)):
        raise CalibrationError(f"{source} ratings must be a list")

    scores: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise CalibrationError(f"{source} rating must be an object")

        criterion_id = row.get("criterion_id")
        score = row.get("score")

        if not isinstance(criterion_id, str) or not criterion_id:
            raise CalibrationError(f"{source} rating needs a criterion_id")
        if criterion_id in scores:
            raise CalibrationError(f"{source} repeats criterion '{criterion_id}'")

        # bool is a subclass of int in Python, but True is not a rubric score.
        if type(score) is not int or score not in (0, 1, 2):
            raise CalibrationError(f"{source} criterion '{criterion_id}' needs score 0, 1, or 2")
        scores[criterion_id] = score

    missing = set(expected_ids) - set(scores)
    extra = set(scores) - set(expected_ids)
    if missing or extra:
        raise CalibrationError(
            f"{source} criterion mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return scores


def pair_selected_attempts(
    selections: Sequence[tuple[JudgeAttempt, HumanLabelSet]],
    *,
    rubric: RubricDefinition,
) -> tuple[CalibrationPair, ...]:
    """Pair one explicitly selected judge attempt and human label per result."""
    if not selections:
        raise CalibrationError("Select at least one judge/human pair")

    expected_ids = tuple(criterion.id for criterion in rubric.criteria)
    rubric_identity = (rubric.id, rubric.version, rubric.content_hash)
    seen_results: set[int] = set()
    seen_judges: set[str] = set()
    seen_labels: set[str] = set()
    pairs: list[CalibrationPair] = []

    for judge, human in selections:
        if judge.result_id != human.result_id:
            raise CalibrationError("Judge attempt and human label must belong to the same result")
        if judge.status != "completed":
            raise CalibrationError(f"Judge attempt '{judge.id}' is not completed")

        judge_identity = (judge.rubric_id, judge.rubric_version, judge.rubric_hash)
        human_identity = (human.rubric_id, human.rubric_version, human.rubric_hash)
        if judge_identity != rubric_identity or human_identity != rubric_identity:
            raise CalibrationError("Judge and human ratings must use the selected rubric version")

        if judge.result_id in seen_results or judge.id in seen_judges or human.id in seen_labels:
            raise CalibrationError(
                "Each result, judge attempt, and human label may be selected once"
            )

        judge_scores = _scores_by_criterion(
            judge.assessments_json,
            expected_ids=expected_ids,
            source="Judge",
        )
        human_scores = _scores_by_criterion(
            human.ratings_json,
            expected_ids=expected_ids,
            source="Human",
        )
        pairs.append(
            CalibrationPair(
                result_id=judge.result_id,
                human_label_id=human.id,
                judge_attempt_id=judge.id,
                rubric_hash=rubric.content_hash,
                criteria=tuple(
                    CriterionPair(
                        criterion_id=criterion_id,
                        human_score=human_scores[criterion_id],
                        judge_score=judge_scores[criterion_id],
                    )
                    for criterion_id in expected_ids
                ),
            )
        )
        seen_results.add(judge.result_id)
        seen_judges.add(judge.id)
        seen_labels.add(human.id)

    return tuple(sorted(pairs, key=lambda pair: pair.result_id))
