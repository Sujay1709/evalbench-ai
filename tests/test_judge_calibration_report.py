from types import SimpleNamespace

import pytest

from evalbench.judges.calibration import (
    CalibrationError,
    CalibrationPair,
    CriterionAgreement,
    CriterionPair,
    build_calibration_report,
    pair_selected_attempts,
    summarize_criterion,
)


def _pair(
    result_id: int,
    *scores: tuple[str, int, int],
    rubric_hash: str = "rubric-hash",
) -> CalibrationPair:
    return CalibrationPair(
        result_id=result_id,
        human_label_id=f"human-{result_id}",
        judge_attempt_id=f"judge-{result_id}",
        rubric_hash=rubric_hash,
        criteria=tuple(
            CriterionPair(
                criterion_id=criterion_id,
                human_score=human_score,
                judge_score=judge_score,
            )
            for criterion_id, human_score, judge_score in scores
        ),
    )


def _calibration_pairs() -> tuple[CalibrationPair, ...]:
    return (
        _pair(1, ("correctness", 2, 2), ("groundedness", 1, 0)),
        _pair(2, ("correctness", 1, 0), ("groundedness", 0, 0)),
        _pair(3, ("correctness", 0, 0), ("groundedness", 2, 1)),
        _pair(4, ("correctness", 2, 1), ("groundedness", 1, 1)),
    )


def test_report_discloses_sample_agreement_confusion_and_disagreements() -> None:
    report = build_calibration_report(
        _calibration_pairs(), bootstrap_resamples=200, bootstrap_seed=17
    )

    assert report.score_labels == (0, 1, 2)
    assert report.overall.result_count == 4
    assert report.overall.rating_count == 8
    assert report.overall.exact_agreement == pytest.approx(0.5)
    assert report.overall.quadratic_weighted_kappa is not None
    assert report.overall.confusion_matrix == (
        (2, 0, 0),
        (2, 1, 0),
        (0, 2, 1),
    )
    assert report.overall.kappa_interval is not None
    assert report.overall.kappa_interval.method == "result-paired percentile bootstrap"
    assert report.overall.kappa_interval.requested_resamples == 200
    assert report.overall.kappa_interval.valid_resamples <= 200
    assert tuple(item.criterion_id for item in report.by_criterion) == (
        "correctness",
        "groundedness",
    )
    assert [
        (item.result_id, item.criterion_id, item.human_score, item.judge_score)
        for item in report.disagreements
    ] == [
        (1, "groundedness", 1, 0),
        (2, "correctness", 1, 0),
        (3, "groundedness", 2, 1),
        (4, "correctness", 2, 1),
    ]


def test_bootstrap_report_is_reproducible_for_a_fixed_seed() -> None:
    first = build_calibration_report(
        _calibration_pairs(), bootstrap_resamples=100, bootstrap_seed=91
    )
    second = build_calibration_report(
        tuple(reversed(_calibration_pairs())),
        bootstrap_resamples=100,
        bootstrap_seed=91,
    )

    assert first == second


def test_report_surfaces_undefined_kappa_without_claiming_zero_agreement() -> None:
    pairs = (
        _pair(1, ("correctness", 2, 2)),
        _pair(2, ("correctness", 2, 2)),
    )

    report = build_calibration_report(pairs, bootstrap_resamples=20)

    assert report.overall.exact_agreement == 1.0
    assert report.overall.quadratic_weighted_kappa is None
    assert report.overall.kappa_interval is None
    assert len(report.advisories) == 2


def test_report_rejects_inputs_that_cannot_form_one_calibration_sample() -> None:
    with pytest.raises(CalibrationError, match="same ordered criteria"):
        build_calibration_report(
            (
                _pair(1, ("correctness", 2, 2)),
                _pair(2, ("groundedness", 2, 2)),
            )
        )

    with pytest.raises(CalibrationError, match="one rubric hash"):
        build_calibration_report(
            (
                _pair(1, ("correctness", 2, 2)),
                _pair(2, ("correctness", 2, 2), rubric_hash="other-rubric"),
            )
        )


def test_pairing_rejects_mixed_judge_configurations() -> None:
    rubric = SimpleNamespace(
        id="grounded_qa",
        version="1.0.0",
        content_hash="rubric-hash",
        criteria=(SimpleNamespace(id="correctness"),),
    )

    def selection(result_id: int, judge_model: str) -> tuple[object, object]:
        judge = SimpleNamespace(
            id=f"judge-{result_id}",
            result_id=result_id,
            status="completed",
            rubric_id=rubric.id,
            rubric_version=rubric.version,
            rubric_hash=rubric.content_hash,
            judge_model=judge_model,
            prompt_version="1.0.0",
            prompt_hash="prompt-hash",
            assessments_json=[{"criterion_id": "correctness", "score": 2}],
        )
        human = SimpleNamespace(
            id=f"human-{result_id}",
            result_id=result_id,
            rubric_id=rubric.id,
            rubric_version=rubric.version,
            rubric_hash=rubric.content_hash,
            ratings_json=[{"criterion_id": "correctness", "score": 2}],
        )
        return judge, human

    with pytest.raises(CalibrationError, match="one judge model"):
        pair_selected_attempts(
            (selection(1, "model-a"), selection(2, "model-b")),
            rubric=rubric,
        )


def test_summarize_criterion_reports_nonconstant_perfect_agreement() -> None:
    agreement = summarize_criterion(
        (
            _pair(1, ("correctness", 0, 0)),
            _pair(2, ("correctness", 1, 1)),
            _pair(3, ("correctness", 2, 2)),
        ),
        "correctness",
    )

    assert isinstance(agreement, CriterionAgreement)
    assert agreement.sample_size == 3
    assert agreement.exact_agreement == 1.0
    assert agreement.quadratic_weighted_kappa == pytest.approx(1.0)
    assert agreement.confusion_matrix == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert agreement.disagreement_result_ids == ()


def test_summarize_criterion_reports_disagreement_result_ids() -> None:
    agreement = summarize_criterion(
        (
            _pair(1, ("correctness", 0, 0)),
            _pair(2, ("correctness", 1, 1)),
            _pair(3, ("correctness", 2, 1)),
        ),
        "correctness",
    )

    assert agreement.exact_agreement == pytest.approx(2 / 3)
    assert agreement.quadratic_weighted_kappa is not None
    assert agreement.confusion_matrix == ((1, 0, 0), (0, 1, 0), (0, 1, 0))
    assert agreement.disagreement_result_ids == (3,)


def test_summarize_criterion_keeps_undefined_kappa_distinct_from_agreement() -> None:
    agreement = summarize_criterion(
        (
            _pair(1, ("correctness", 1, 1)),
            _pair(2, ("correctness", 1, 1)),
            _pair(3, ("correctness", 1, 1)),
        ),
        "correctness",
    )

    assert agreement.exact_agreement == 1.0
    assert agreement.quadratic_weighted_kappa is None
