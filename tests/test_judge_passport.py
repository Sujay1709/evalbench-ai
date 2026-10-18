from pathlib import Path

import pytest

from evalbench.datasets import EvaluationSplit
from evalbench.gates import GateConfigError, load_gate_config
from evalbench.gates.config import (
    BenchmarkSpec,
    GateConfig,
    GatePolicy,
    JudgeGateDeclaration,
)
from evalbench.gates.runner import run_gate
from evalbench.judges.calibration import (
    AgreementStatistics,
    CalibrationReport,
    KappaConfidenceInterval,
)
from evalbench.judges.pairwise import PairwiseJudgment, summarize_order_swaps
from evalbench.judges.passport import (
    VerbosityProbe,
    build_judge_passport,
    release_gate_block,
)
from evalbench.judges.repeatability import (
    RepeatedJudgment,
    RepeatedScore,
    summarize_repeated_judgments,
)
from evalbench.providers.mock import MockProvider
from tests.conftest import PROJECT_ROOT

JUDGE_ID = "mock-judge"
RUBRIC_ID = "grounded-qa"
RUBRIC_VERSION = "v1"
RUBRIC_HASH = "ab" * 32
GATE_CONFIG = PROJECT_ROOT / "regression" / "gate.yaml"


def _repeatability(second_score: int = 2):
    attempts = [
        RepeatedJudgment(
            attempt_id=attempt_id,
            result_id=1,
            status="completed",
            rubric_id=RUBRIC_ID,
            rubric_version=RUBRIC_VERSION,
            rubric_hash=RUBRIC_HASH,
            judge_model=JUDGE_ID,
            prompt_version="v1",
            prompt_hash=RUBRIC_HASH,
            scores=(RepeatedScore("faithfulness", score),),
        )
        for attempt_id, score in (("attempt-1", 2), ("attempt-2", second_score))
    ]
    return summarize_repeated_judgments(attempts)


def _order_swaps(*, flip: bool = False, split: str = "holdout"):
    ba_preference = 2 if flip else 1
    shared = {
        "comparison_id": "pair-1",
        "result_a_id": 1,
        "result_b_id": 2,
        "dataset_split": split,
        "status": "completed",
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        "rubric_hash": RUBRIC_HASH,
        "judge_model": JUDGE_ID,
        "prompt_version": "v1",
        "prompt_template_hash": RUBRIC_HASH,
    }
    return summarize_order_swaps(
        [
            PairwiseJudgment(
                attempt_id="ab",
                presentation_order=(1, 2),
                preferred_result_id=1,
                **shared,
            ),
            PairwiseJudgment(
                attempt_id="ba",
                presentation_order=(2, 1),
                preferred_result_id=ba_preference,
                **shared,
            ),
        ]
    )


def _calibration(*, results: int = 10, lower: float = 0.8) -> CalibrationReport:
    return CalibrationReport(
        rubric_hash=RUBRIC_HASH,
        score_labels=(0, 1, 2),
        overall=AgreementStatistics(
            result_count=results,
            rating_count=results,
            exact_agreement=1.0,
            quadratic_weighted_kappa=1.0,
            kappa_interval=KappaConfidenceInterval(
                low=lower,
                high=1.0,
                confidence_level=0.95,
                method="supplied-fixture",
                requested_resamples=100,
                valid_resamples=100,
            ),
            confusion_matrix=((results, 0, 0), (0, 0, 0), (0, 0, 0)),
        ),
        by_criterion=(),
        disagreements=(),
        bootstrap_seed=0,
        bootstrap_resamples=100,
        advisories=(),
    )


def _verbosity(long_rating: int = 2) -> VerbosityProbe:
    return VerbosityProbe(("faithfulness",), (2,), (long_rating,))


def _passport(**overrides):
    values = {
        "judge_id": JUDGE_ID,
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        "rubric_hash": RUBRIC_HASH,
        "repeatability": _repeatability(),
        "order_swaps": _order_swaps(),
        "calibration_report": _calibration(),
        "calibration_split": "holdout",
        "verbosity": _verbosity(),
        "deterministic_scores_remain_authoritative": True,
    }
    values.update(overrides)
    return build_judge_passport(**values)


def _declaration() -> JudgeGateDeclaration:
    return JudgeGateDeclaration(
        judge_id=JUDGE_ID,
        rubric_id=RUBRIC_ID,
        rubric_version=RUBRIC_VERSION,
        rubric_hash=RUBRIC_HASH,
    )


def _judge_config() -> GateConfig:
    return GateConfig(
        version=1,
        policy=GatePolicy(
            max_newly_failing=0,
            mean_score_tolerance=0.02,
            confidence_level=0.95,
            bootstrap_resamples=100,
            bootstrap_seed=1,
        ),
        judge=_declaration(),
        benchmarks={
            "sample": BenchmarkSpec(
                dataset=Path("missing.jsonl"),
                prompt=Path("missing.yaml"),
                split=EvaluationSplit.DEVELOPMENT,
            )
        },
        tiers={"smoke": ["sample"]},
        source=Path("gate.yaml"),
    )


def test_supplied_evidence_can_pass_every_passport_section():
    passport = _passport()
    agreement = next(section for section in passport.sections if section.name == "human_agreement")

    assert passport.allows_release_gate is True
    assert passport.failures == ()
    assert "confusion matrix" in agreement.evidence
    assert "flip rate 0.000" in next(
        section.evidence for section in passport.sections if section.name == "order_swaps"
    )
    assert "matched on faithfulness" in next(
        section.evidence for section in passport.sections if section.name == "verbosity"
    )
    assert release_gate_block(passport, _declaration()) is None


def test_a_judge_without_human_agreement_cannot_gate_a_release():
    passport = _passport(calibration_report=None, calibration_split=None)

    assert passport.allows_release_gate is False
    assert any("human-reviewed holdout" in failure for failure in passport.failures)


def test_verbosity_and_order_changes_are_named_in_the_refusal():
    verbose = _passport(verbosity=_verbosity(long_rating=1))
    flipped = _passport(order_swaps=_order_swaps(flip=True))
    unstable = _passport(repeatability=_repeatability(second_score=1))

    assert any("faithfulness 2 to 1" in failure for failure in verbose.failures)
    assert any("Answer order changed" in failure for failure in flipped.failures)
    assert any("Repeated scores disagreed" in failure for failure in unstable.failures)


def test_development_order_swaps_and_a_replacing_judge_are_refused():
    development = _passport(order_swaps=_order_swaps(split="development"))
    replacing = _passport(deterministic_scores_remain_authoritative=False)

    assert any("holdout split" in failure for failure in development.failures)
    assert any("cannot replace exact match" in failure for failure in replacing.failures)


def test_the_shipped_gate_stays_deterministic_and_refuses_a_passport():
    config = load_gate_config(GATE_CONFIG)

    assert config.judge is None
    with pytest.raises(GateConfigError, match="deterministic checks"):
        run_gate(
            config,
            tier="smoke",
            provider=MockProvider(),
            judge_passport=_passport(),
        )


def test_a_declared_judge_is_refused_until_its_passport_matches_and_passes():
    config = _judge_config()

    with pytest.raises(GateConfigError, match="no passport was supplied"):
        run_gate(config, tier="smoke", provider=MockProvider())
    with pytest.raises(GateConfigError, match="human-reviewed holdout"):
        run_gate(
            config,
            tier="smoke",
            provider=MockProvider(),
            judge_passport=_passport(calibration_report=None),
        )

    other = _declaration().model_copy(update={"judge_id": "other-judge"})
    assert release_gate_block(_passport(), other) == (
        "Judge passport does not match the judge declared by the gate config"
    )

    report = run_gate(
        config, tier="smoke", provider=MockProvider(), judge_passport=_passport()
    )
    assert report.status == "error"
    assert report.outcomes[0].error is not None
    assert "not found" in report.outcomes[0].error.casefold()
