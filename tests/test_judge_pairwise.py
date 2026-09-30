"""Offline contracts for order-swapped pairwise judge summaries."""

from dataclasses import replace

import pytest

from evalbench.judges.pairwise import (
    PairwiseCalibrationError,
    PairwiseJudgment,
    summarize_order_swaps,
)


def _pair(
    *,
    ab_winner: int | None = 11,
    ba_winner: int | None = 11,
    comparison_id: str = "comparison-1",
) -> tuple[PairwiseJudgment, PairwiseJudgment]:
    shared = {
        "comparison_id": comparison_id,
        "result_a_id": 11,
        "result_b_id": 22,
        "dataset_split": "development",
        "status": "completed",
        "rubric_id": "grounded_qa",
        "rubric_version": "1.0.0",
        "rubric_hash": "rubric-sha",
        "judge_model": "test-judge",
        "prompt_version": "v1",
        "prompt_template_hash": "prompt-template-sha",
    }
    return (
        PairwiseJudgment(
            attempt_id=f"{comparison_id}-ab",
            presentation_order=(11, 22),
            preferred_result_id=ab_winner,
            **shared,
        ),
        PairwiseJudgment(
            attempt_id=f"{comparison_id}-ba",
            presentation_order=(22, 11),
            preferred_result_id=ba_winner,
            **shared,
        ),
    )


def test_consistent_candidate_preference_is_not_a_position_flip() -> None:
    report = summarize_order_swaps(_pair())

    assert report.comparison_count == 1
    assert report.preference_flip_count == 0
    assert report.preference_flip_rate == 0.0
    assert report.first_position_wins == 1
    assert report.decisive_judgment_count == 2
    assert report.first_position_win_rate == 0.5
    assert report.comparisons[0].preference_changed is False


def test_preference_reversal_that_follows_first_position_is_reported() -> None:
    report = summarize_order_swaps(_pair(ab_winner=11, ba_winner=22))

    assert report.preference_flip_count == 1
    assert report.preference_flip_rate == 1.0
    assert report.first_position_wins == 2
    assert report.first_position_win_rate == 1.0
    assert report.comparisons[0].preference_changed is True


def test_two_ties_are_stable_but_do_not_create_a_position_win_rate() -> None:
    report = summarize_order_swaps(_pair(ab_winner=None, ba_winner=None))

    assert report.preference_flip_rate == 0.0
    assert report.decisive_judgment_count == 0
    assert report.first_position_win_rate is None


@pytest.mark.parametrize(
    ("judgments", "message"),
    [
        ((), "At least one complete"),
        (_pair()[0:1], "exactly one judgment in each order"),
        (
            (
                _pair()[0],
                replace(_pair()[1], presentation_order=(11, 22)),
            ),
            "one A/B and one B/A",
        ),
        (
            (
                _pair()[0],
                replace(_pair()[1], preferred_result_id=99),
            ),
            "one of the compared results",
        ),
        (
            (
                _pair()[0],
                replace(_pair()[1], judge_model="different-model"),
            ),
            "one dataset split, rubric, judge model",
        ),
        (
            (
                _pair()[0],
                replace(_pair()[1], dataset_split="holdout"),
            ),
            "one dataset split",
        ),
        (
            tuple(
                replace(item, dataset_split="legacy_mixed")
                for item in _pair()
            ),
            "explicit development or holdout",
        ),
    ],
)
def test_incomplete_or_incomparable_evidence_is_rejected(judgments, message) -> None:
    with pytest.raises(PairwiseCalibrationError, match=message):
        summarize_order_swaps(judgments)
