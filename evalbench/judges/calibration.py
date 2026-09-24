"""Pair explicitly selected human and judge ratings for calibration."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sklearn.metrics import cohen_kappa_score
from sklearn.metrics import confusion_matrix as sklearn_confusion_matrix

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


@dataclass(frozen=True)
class CriterionAgreement:
    """Deterministic agreement summary for one rubric criterion."""

    criterion_id: str
    sample_size: int
    exact_agreement: float
    quadratic_weighted_kappa: float | None
    confusion_matrix: tuple[tuple[int, ...], ...]
    disagreement_result_ids: tuple[int, ...]


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
    selected_judge_identity: tuple[str, str, str] | None = None
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

        judge_configuration = (
            judge.judge_model,
            judge.prompt_version,
            judge.prompt_hash,
        )
        if selected_judge_identity is None:
            selected_judge_identity = judge_configuration
        elif judge_configuration != selected_judge_identity:
            raise CalibrationError(
                "Calibration pairs must use one judge model and prompt configuration"
            )

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


SCORE_LABELS = (0, 1, 2)


@dataclass(frozen=True)
class KappaConfidenceInterval:
    low: float
    high: float
    confidence_level: float
    method: str
    requested_resamples: int
    valid_resamples: int


@dataclass(frozen=True)
class AgreementStatistics:
    result_count: int
    rating_count: int
    exact_agreement: float
    quadratic_weighted_kappa: float | None
    kappa_interval: KappaConfidenceInterval | None
    confusion_matrix: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class CriterionCalibration:
    criterion_id: str
    statistics: AgreementStatistics


@dataclass(frozen=True)
class CalibrationDisagreement:
    result_id: int
    human_label_id: str
    judge_attempt_id: str
    criterion_id: str
    human_score: int
    judge_score: int


@dataclass(frozen=True)
class CalibrationReport:
    rubric_hash: str
    score_labels: tuple[int, ...]
    overall: AgreementStatistics
    by_criterion: tuple[CriterionCalibration, ...]
    disagreements: tuple[CalibrationDisagreement, ...]
    bootstrap_seed: int
    bootstrap_resamples: int
    advisories: tuple[str, ...]


def _validate_report_inputs(pairs: Sequence[CalibrationPair]) -> tuple[CalibrationPair, ...]:
    if not pairs:
        raise CalibrationError("At least one calibration pair is required")

    ordered_pairs = tuple(sorted(pairs, key=lambda pair: pair.result_id))
    first = ordered_pairs[0]
    expected_criteria = tuple(row.criterion_id for row in first.criteria)
    if not expected_criteria or len(set(expected_criteria)) != len(expected_criteria):
        raise CalibrationError("Calibration pairs need unique criterion IDs")

    seen_results: set[int] = set()
    for pair in ordered_pairs:
        if pair.result_id in seen_results:
            raise CalibrationError(f"Result '{pair.result_id}' appears more than once")
        if pair.rubric_hash != first.rubric_hash:
            raise CalibrationError("Calibration pairs must use one rubric hash")
        if tuple(row.criterion_id for row in pair.criteria) != expected_criteria:
            raise CalibrationError("Calibration pairs must contain the same ordered criteria")
        for row in pair.criteria:
            if row.human_score not in SCORE_LABELS or row.judge_score not in SCORE_LABELS:
                raise CalibrationError("Calibration scores must be 0, 1, or 2")
        seen_results.add(pair.result_id)
    return ordered_pairs


def _rating_vectors(
    pairs: Sequence[CalibrationPair], *, criterion_id: str | None
) -> tuple[list[int], list[int]]:
    human_scores: list[int] = []
    judge_scores: list[int] = []
    for pair in pairs:
        for row in pair.criteria:
            if criterion_id is None or row.criterion_id == criterion_id:
                human_scores.append(row.human_score)
                judge_scores.append(row.judge_score)
    return human_scores, judge_scores


def _weighted_kappa(human_scores: Sequence[int], judge_scores: Sequence[int]) -> float | None:
    if len(set(human_scores)) == 1 and human_scores == judge_scores:
        return None
    value = float(
        cohen_kappa_score(
            human_scores,
            judge_scores,
            labels=list(SCORE_LABELS),
            weights="quadratic",
        )
    )
    return value if math.isfinite(value) else None


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    weight = position - lower_index
    return (
        sorted_values[lower_index] * (1.0 - weight)
        + sorted_values[upper_index] * weight
    )


def _bootstrap_kappa_interval(
    pairs: Sequence[CalibrationPair],
    *,
    criterion_id: str | None,
    confidence_level: float,
    resamples: int,
    seed: int,
) -> KappaConfidenceInterval | None:
    if len(pairs) < 2:
        return None

    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled = tuple(pairs[generator.randrange(len(pairs))] for _ in pairs)
        human_scores, judge_scores = _rating_vectors(
            sampled, criterion_id=criterion_id
        )
        estimate = _weighted_kappa(human_scores, judge_scores)
        if estimate is not None:
            estimates.append(estimate)

    if len(estimates) < 2:
        return None
    estimates.sort()
    tail_probability = (1.0 - confidence_level) / 2.0
    return KappaConfidenceInterval(
        low=_percentile(estimates, tail_probability),
        high=_percentile(estimates, 1.0 - tail_probability),
        confidence_level=confidence_level,
        method="result-paired percentile bootstrap",
        requested_resamples=resamples,
        valid_resamples=len(estimates),
    )


def _agreement_statistics(
    pairs: Sequence[CalibrationPair],
    *,
    criterion_id: str | None,
    confidence_level: float,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> AgreementStatistics:
    human_scores, judge_scores = _rating_vectors(pairs, criterion_id=criterion_id)
    matrix = sklearn_confusion_matrix(
        human_scores,
        judge_scores,
        labels=list(SCORE_LABELS),
    )
    return AgreementStatistics(
        result_count=len(pairs),
        rating_count=len(human_scores),
        exact_agreement=sum(
            human == judge for human, judge in zip(human_scores, judge_scores, strict=True)
        )
        / len(human_scores),
        quadratic_weighted_kappa=_weighted_kappa(human_scores, judge_scores),
        kappa_interval=_bootstrap_kappa_interval(
            pairs,
            criterion_id=criterion_id,
            confidence_level=confidence_level,
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        ),
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
    )


def summarize_criterion(
    pairs: Sequence[CalibrationPair], criterion_id: str
) -> CriterionAgreement:
    """Summarize one criterion without persisting data or calling a model."""
    if not isinstance(criterion_id, str) or not criterion_id:
        raise CalibrationError("criterion_id must be a non-empty string")

    ordered_pairs = _validate_report_inputs(pairs)
    available_criteria = tuple(row.criterion_id for row in ordered_pairs[0].criteria)
    if criterion_id not in available_criteria:
        raise CalibrationError(
            f"Criterion '{criterion_id}' is not present in selected calibration pairs"
        )

    human_scores, judge_scores = _rating_vectors(
        ordered_pairs, criterion_id=criterion_id
    )
    matrix = sklearn_confusion_matrix(
        human_scores,
        judge_scores,
        labels=list(SCORE_LABELS),
    )
    disagreement_result_ids = tuple(
        pair.result_id
        for pair in ordered_pairs
        for row in pair.criteria
        if row.criterion_id == criterion_id and row.human_score != row.judge_score
    )
    return CriterionAgreement(
        criterion_id=criterion_id,
        sample_size=len(ordered_pairs),
        exact_agreement=sum(
            human == judge
            for human, judge in zip(human_scores, judge_scores, strict=True)
        )
        / len(human_scores),
        quadratic_weighted_kappa=_weighted_kappa(human_scores, judge_scores),
        confusion_matrix=tuple(tuple(int(value) for value in row) for row in matrix),
        disagreement_result_ids=disagreement_result_ids,
    )


def build_calibration_report(
    pairs: Sequence[CalibrationPair],
    *,
    confidence_level: float = 0.95,
    bootstrap_resamples: int = 2_000,
    bootstrap_seed: int = 0,
) -> CalibrationReport:
    """Summarize ordinal judge agreement with result-paired uncertainty."""
    if not 0.0 < confidence_level < 1.0:
        raise CalibrationError("confidence_level must be between 0 and 1")
    if type(bootstrap_resamples) is not int or bootstrap_resamples < 1:
        raise CalibrationError("bootstrap_resamples must be a positive integer")
    if type(bootstrap_seed) is not int:
        raise CalibrationError("bootstrap_seed must be an integer")

    ordered_pairs = _validate_report_inputs(pairs)
    criterion_ids = tuple(row.criterion_id for row in ordered_pairs[0].criteria)
    overall = _agreement_statistics(
        ordered_pairs,
        criterion_id=None,
        confidence_level=confidence_level,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    by_criterion = tuple(
        CriterionCalibration(
            criterion_id=criterion_id,
            statistics=_agreement_statistics(
                ordered_pairs,
                criterion_id=criterion_id,
                confidence_level=confidence_level,
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_seed=bootstrap_seed,
            ),
        )
        for criterion_id in criterion_ids
    )
    disagreements = tuple(
        CalibrationDisagreement(
            result_id=pair.result_id,
            human_label_id=pair.human_label_id,
            judge_attempt_id=pair.judge_attempt_id,
            criterion_id=row.criterion_id,
            human_score=row.human_score,
            judge_score=row.judge_score,
        )
        for pair in ordered_pairs
        for row in pair.criteria
        if row.human_score != row.judge_score
    )

    advisories: list[str] = []
    if overall.quadratic_weighted_kappa is None:
        advisories.append(
            "Weighted kappa is undefined because the selected ratings have no score variation."
        )
    if overall.kappa_interval is None:
        advisories.append(
            "A bootstrap interval could not be estimated from the selected results."
        )

    return CalibrationReport(
        rubric_hash=ordered_pairs[0].rubric_hash,
        score_labels=SCORE_LABELS,
        overall=overall,
        by_criterion=by_criterion,
        disagreements=disagreements,
        bootstrap_seed=bootstrap_seed,
        bootstrap_resamples=bootstrap_resamples,
        advisories=tuple(advisories),
    )
