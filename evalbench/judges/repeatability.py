"""Pure consistency summaries for repeated calls to the same judge configuration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations


class RepeatabilityError(ValueError):
    """Repeated judge attempts are not a comparable, complete sample."""


@dataclass(frozen=True)
class RepeatedScore:
    criterion_id: str
    score: int


@dataclass(frozen=True)
class RepeatedJudgment:
    attempt_id: str
    result_id: int
    status: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    judge_model: str
    prompt_version: str
    prompt_hash: str
    scores: tuple[RepeatedScore, ...]


@dataclass(frozen=True)
class CriterionRepeatability:
    criterion_id: str
    pair_count: int
    exact_agreement: float
    score_min: int
    score_max: int
    disagreement_attempt_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RepeatabilityReport:
    result_id: int
    judge_model: str
    prompt_version: str
    prompt_hash: str
    attempt_ids: tuple[str, ...]
    attempt_pair_count: int
    rating_pair_count: int
    exact_agreement: float
    criteria: tuple[CriterionRepeatability, ...]


def summarize_repeated_judgments(
    attempts: Sequence[RepeatedJudgment],
) -> RepeatabilityReport:
    """Measure score agreement across repeated attempts on one exact request.

    Each attempt pair is compared once per rubric criterion. The returned
    agreement is the fraction of those criterion-level comparisons with an
    identical 0/1/2 score. This describes consistency, not correctness.
    """
    if len(attempts) < 2:
        raise RepeatabilityError("At least two completed judge attempts are required")

    ordered = tuple(sorted(attempts, key=lambda attempt: attempt.attempt_id))
    identity = (
        ordered[0].result_id,
        ordered[0].rubric_id,
        ordered[0].rubric_version,
        ordered[0].rubric_hash,
        ordered[0].judge_model,
        ordered[0].prompt_version,
        ordered[0].prompt_hash,
    )
    if len({attempt.attempt_id for attempt in ordered}) != len(ordered):
        raise RepeatabilityError("Repeated judge attempt IDs must be unique")

    expected_criteria = tuple(score.criterion_id for score in ordered[0].scores)
    if not expected_criteria or len(set(expected_criteria)) != len(expected_criteria):
        raise RepeatabilityError("Repeated judgments need unique rubric criterion IDs")

    scores_by_attempt: dict[str, dict[str, int]] = {}
    for attempt in ordered:
        attempt_identity = (
            attempt.result_id,
            attempt.rubric_id,
            attempt.rubric_version,
            attempt.rubric_hash,
            attempt.judge_model,
            attempt.prompt_version,
            attempt.prompt_hash,
        )
        if attempt_identity != identity:
            raise RepeatabilityError(
                "Repeatability comparisons require one result, rubric, judge model, and prompt hash"
            )
        if attempt.status != "completed":
            raise RepeatabilityError("Only completed judge attempts can be compared")
        criteria = tuple(score.criterion_id for score in attempt.scores)
        if criteria != expected_criteria:
            raise RepeatabilityError(
                "Repeated judgments must contain the same ordered rubric criteria"
            )
        score_map: dict[str, int] = {}
        for score in attempt.scores:
            if (
                not isinstance(score.criterion_id, str)
                or not score.criterion_id
                or type(score.score) is not int
                or score.score not in (0, 1, 2)
            ):
                raise RepeatabilityError("Repeated rubric scores must be integers from 0 to 2")
            score_map[score.criterion_id] = score.score
        scores_by_attempt[attempt.attempt_id] = score_map

    attempt_pairs = tuple(combinations((attempt.attempt_id for attempt in ordered), 2))
    criteria_reports: list[CriterionRepeatability] = []
    matching_rating_pairs = 0
    for criterion_id in expected_criteria:
        disagreements = tuple(
            (first_id, second_id)
            for first_id, second_id in attempt_pairs
            if scores_by_attempt[first_id][criterion_id]
            != scores_by_attempt[second_id][criterion_id]
        )
        pair_count = len(attempt_pairs)
        matching_rating_pairs += pair_count - len(disagreements)
        criterion_scores = [
            scores_by_attempt[attempt.attempt_id][criterion_id] for attempt in ordered
        ]
        criteria_reports.append(
            CriterionRepeatability(
                criterion_id=criterion_id,
                pair_count=pair_count,
                exact_agreement=(pair_count - len(disagreements)) / pair_count,
                score_min=min(criterion_scores),
                score_max=max(criterion_scores),
                disagreement_attempt_pairs=disagreements,
            )
        )

    rating_pair_count = len(attempt_pairs) * len(expected_criteria)
    return RepeatabilityReport(
        result_id=identity[0],
        judge_model=identity[4],
        prompt_version=identity[5],
        prompt_hash=identity[6],
        attempt_ids=tuple(attempt.attempt_id for attempt in ordered),
        attempt_pair_count=len(attempt_pairs),
        rating_pair_count=rating_pair_count,
        exact_agreement=matching_rating_pairs / rating_pair_count,
        criteria=tuple(criteria_reports),
    )
