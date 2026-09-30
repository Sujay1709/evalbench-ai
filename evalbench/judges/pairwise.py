"""Pure summaries for order-swapped pairwise judge evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class PairwiseCalibrationError(ValueError):
    """Pairwise judgments do not form complete, comparable order swaps."""


@dataclass(frozen=True)
class PairwiseJudgment:
    """One completed judge choice between two results in a presented order."""

    attempt_id: str
    comparison_id: str
    result_a_id: int
    result_b_id: int
    presentation_order: tuple[int, int]
    preferred_result_id: int | None
    dataset_split: str
    status: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    judge_model: str
    prompt_version: str
    prompt_template_hash: str


@dataclass(frozen=True)
class PairwiseComparison:
    """Normalized outcome for one comparison in both presentation orders."""

    comparison_id: str
    result_a_id: int
    result_b_id: int
    ab_preference: int | None
    ba_preference: int | None
    preference_changed: bool
    first_position_wins: int
    decisive_judgments: int


@dataclass(frozen=True)
class PairwiseOrderSwapReport:
    """Aggregate preference consistency and first-position preference evidence."""

    judge_model: str
    dataset_split: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    prompt_version: str
    prompt_template_hash: str
    comparison_count: int
    preference_flip_count: int
    preference_flip_rate: float
    first_position_wins: int
    decisive_judgment_count: int
    first_position_win_rate: float | None
    comparisons: tuple[PairwiseComparison, ...]


def summarize_order_swaps(
    judgments: Sequence[PairwiseJudgment],
) -> PairwiseOrderSwapReport:
    """Compare one A/B judgment with its B/A counterpart for each result pair.

    A preference flip means the normalized winner changed, including a decisive
    choice changing to a tie or vice versa. The first-position win rate excludes
    ties; it is descriptive position evidence, not proof of causal bias.
    """
    if not judgments:
        raise PairwiseCalibrationError("At least one complete order-swapped comparison is required")

    attempt_ids = [item.attempt_id for item in judgments]
    if (
        any(not isinstance(item, str) or not item for item in attempt_ids)
        or len(set(attempt_ids)) != len(attempt_ids)
    ):
        raise PairwiseCalibrationError("Pairwise attempt IDs must be nonblank and unique")

    first = judgments[0]
    configuration = (
        first.dataset_split,
        first.rubric_id,
        first.rubric_version,
        first.rubric_hash,
        first.judge_model,
        first.prompt_version,
        first.prompt_template_hash,
    )
    grouped: dict[str, list[PairwiseJudgment]] = {}
    for item in judgments:
        item_configuration = (
            item.dataset_split,
            item.rubric_id,
            item.rubric_version,
            item.rubric_hash,
            item.judge_model,
            item.prompt_version,
            item.prompt_template_hash,
        )
        if item_configuration != configuration:
            raise PairwiseCalibrationError(
                "Order-swap reports require one dataset split, rubric, judge model, "
                "and prompt template"
            )
        if item.dataset_split not in ("development", "holdout"):
            raise PairwiseCalibrationError(
                "Pairwise calibration requires an explicit development or holdout split"
            )
        if item.status != "completed":
            raise PairwiseCalibrationError("Only completed pairwise judgments can be compared")
        if (
            type(item.result_a_id) is not int
            or type(item.result_b_id) is not int
            or item.result_a_id <= 0
            or item.result_b_id <= 0
            or item.result_a_id == item.result_b_id
        ):
            raise PairwiseCalibrationError("A comparison must contain two distinct result IDs")
        expected_results = {item.result_a_id, item.result_b_id}
        if (
            not isinstance(item.presentation_order, tuple)
            or len(item.presentation_order) != 2
            or any(type(result_id) is not int for result_id in item.presentation_order)
            or set(item.presentation_order) != expected_results
        ):
            raise PairwiseCalibrationError(
                "Presentation order must contain each compared result exactly once"
            )
        if item.preferred_result_id is not None and (
            type(item.preferred_result_id) is not int
            or item.preferred_result_id not in expected_results
        ):
            raise PairwiseCalibrationError(
                "The preferred result must be one of the compared results or a tie"
            )
        if not isinstance(item.comparison_id, str) or not item.comparison_id:
            raise PairwiseCalibrationError("Comparison IDs must not be blank")
        grouped.setdefault(item.comparison_id, []).append(item)

    comparisons: list[PairwiseComparison] = []
    for comparison_id, pair in sorted(grouped.items()):
        if len(pair) != 2:
            raise PairwiseCalibrationError(
                f"Comparison '{comparison_id}' needs exactly one judgment in each order"
            )
        ordered_pair = sorted(
            pair,
            key=lambda item: item.presentation_order
            != (item.result_a_id, item.result_b_id),
        )
        ab, ba = ordered_pair
        if (ab.result_a_id, ab.result_b_id) != (ba.result_a_id, ba.result_b_id):
            raise PairwiseCalibrationError(
                f"Comparison '{comparison_id}' must use the same result identities"
            )
        if ab.presentation_order != (ab.result_a_id, ab.result_b_id) or ba.presentation_order != (
            ba.result_b_id,
            ba.result_a_id,
        ):
            raise PairwiseCalibrationError(
                f"Comparison '{comparison_id}' must include one A/B and one B/A presentation"
            )
        decisive = sum(item.preferred_result_id is not None for item in (ab, ba))
        first_wins = sum(
            item.preferred_result_id == item.presentation_order[0]
            for item in (ab, ba)
        )
        comparisons.append(
            PairwiseComparison(
                comparison_id=comparison_id,
                result_a_id=ab.result_a_id,
                result_b_id=ab.result_b_id,
                ab_preference=ab.preferred_result_id,
                ba_preference=ba.preferred_result_id,
                preference_changed=ab.preferred_result_id != ba.preferred_result_id,
                first_position_wins=first_wins,
                decisive_judgments=decisive,
            )
        )

    comparison_count = len(comparisons)
    flip_count = sum(item.preference_changed for item in comparisons)
    first_wins = sum(item.first_position_wins for item in comparisons)
    decisive_count = sum(item.decisive_judgments for item in comparisons)
    return PairwiseOrderSwapReport(
        judge_model=configuration[4],
        dataset_split=configuration[0],
        rubric_id=configuration[1],
        rubric_version=configuration[2],
        rubric_hash=configuration[3],
        prompt_version=configuration[5],
        prompt_template_hash=configuration[6],
        comparison_count=comparison_count,
        preference_flip_count=flip_count,
        preference_flip_rate=flip_count / comparison_count,
        first_position_wins=first_wins,
        decisive_judgment_count=decisive_count,
        first_position_win_rate=(
            first_wins / decisive_count if decisive_count else None
        ),
        comparisons=tuple(comparisons),
    )
