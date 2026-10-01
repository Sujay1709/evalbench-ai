"""Offline checks for the configurable, holdout-only judge readiness policy."""

import pytest

from evalbench.judges.calibration import (
    CalibrationPair,
    CriterionPair,
    build_calibration_report,
)
from evalbench.judges.calibration_gate import (
    CalibrationReadinessPolicy,
    assess_calibration_readiness,
)


def _perfect_pairs() -> tuple[CalibrationPair, ...]:
    return tuple(
        CalibrationPair(
            result_id=result_id,
            human_label_id=f"human-{result_id}",
            judge_attempt_id=f"judge-{result_id}",
            rubric_hash="rubric-v1",
            criteria=(
                CriterionPair("answer_quality", score, score),
                CriterionPair("evidence_alignment", score, score),
            ),
        )
        for result_id, score in enumerate((0, 1, 2, 0), start=1)
    )


def test_holdout_readiness_passes_only_when_sample_and_confidence_thresholds_pass():
    report = build_calibration_report(_perfect_pairs(), bootstrap_resamples=200, bootstrap_seed=8)
    policy = CalibrationReadinessPolicy(
        minimum_results=4,
        minimum_exact_agreement=0.9,
        minimum_kappa_lower_bound=0.8,
    )

    readiness = assess_calibration_readiness(report, dataset_split="holdout", policy=policy)

    assert readiness.eligible is True
    assert readiness.failures == ()
    assert len(readiness.checks) == 3


def test_readiness_rejects_development_small_samples_and_low_agreement():
    report = build_calibration_report(_perfect_pairs(), bootstrap_resamples=50, bootstrap_seed=8)
    policy = CalibrationReadinessPolicy(minimum_results=10)

    readiness = assess_calibration_readiness(report, dataset_split="development", policy=policy)

    assert readiness.eligible is False
    assert len(readiness.failures) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_results": 1},
        {"minimum_exact_agreement": 1.1},
        {"minimum_kappa_lower_bound": -1.1},
    ],
)
def test_readiness_policy_rejects_invalid_thresholds(kwargs):
    with pytest.raises(ValueError):
        CalibrationReadinessPolicy(**kwargs)
