"""Offline checks for split-safe, read-only calibration cohort loading."""

import pytest

from evalbench.extensions import db
from evalbench.judges.calibration import CalibrationError, load_calibration_cohort
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun, ExampleResult, HumanLabelSet, JudgeAttempt
from tests.conftest import PROJECT_ROOT

RUBRIC_PATH = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"


def _run(run_id: str, dataset_split: str) -> EvaluationRun:
    run = EvaluationRun(
        id=run_id,
        correlation_id=f"correlation-{run_id}",
        dataset_name="fixture",
        dataset_version="v1",
        dataset_hash="a" * 64,
        dataset_split=dataset_split,
        prompt_id="grounded_qa",
        prompt_version="v1",
        provider="mock",
        status="completed",
    )
    db.session.add(run)
    return run


def _evidence(
    run: EvaluationRun,
    *,
    suffix: str,
    human_score: int = 2,
    judge_score: int = 2,
) -> tuple[JudgeAttempt, HumanLabelSet]:
    rubric = load_rubric(RUBRIC_PATH)
    result = ExampleResult(
        run=run,
        example_id=f"example-{suffix}",
        input_json={"question": "Fixture question"},
        output_text="Fixture response",
        passed=True,
        score=1.0,
        scorer_details={},
    )
    db.session.add(result)
    db.session.flush()
    judge = JudgeAttempt(
        id=f"judge-{suffix}",
        result_id=result.id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        prompt_version="v1",
        prompt_hash="b" * 64,
        request_text="Fixture request",
        judge_model="fixture-judge",
        status="completed",
        assessments_json=[
            {"criterion_id": "answer_quality", "score": judge_score},
            {"criterion_id": "evidence_alignment", "score": judge_score},
        ],
    )
    human = HumanLabelSet(
        id=f"human-{suffix}",
        result_id=result.id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        annotator_id="labeler_01",
        presentation_hash="c" * 64,
        ratings_json=[
            {"criterion_id": "answer_quality", "score": human_score},
            {"criterion_id": "evidence_alignment", "score": human_score},
        ],
    )
    db.session.add_all((judge, human))
    return judge, human


def test_loader_is_read_only_split_safe_and_order_independent(app) -> None:
    rubric = load_rubric(RUBRIC_PATH)
    with app.app_context():
        run = _run("development-run", "development")
        first = _evidence(run, suffix="first")
        second = _evidence(run, suffix="second", human_score=1, judge_score=2)
        db.session.commit()
        before = (
            db.session.execute(db.select(JudgeAttempt)).scalars().all(),
            db.session.execute(db.select(HumanLabelSet)).scalars().all(),
        )

        reversed_cohort = load_calibration_cohort(
            run.id,
            ((second[0].id, second[1].id), (first[0].id, first[1].id)),
            rubric=rubric,
        )
        ordered_cohort = load_calibration_cohort(
            run.id,
            ((first[0].id, first[1].id), (second[0].id, second[1].id)),
            rubric=rubric,
        )

        assert reversed_cohort == ordered_cohort
        assert reversed_cohort.dataset_split == "development"
        assert [pair.result_id for pair in reversed_cohort.pairs] == sorted(
            pair.result_id for pair in reversed_cohort.pairs
        )
        after = (
            db.session.execute(db.select(JudgeAttempt)).scalars().all(),
            db.session.execute(db.select(HumanLabelSet)).scalars().all(),
        )
        assert [(item.id, item.result_id) for item in after[0]] == [
            (item.id, item.result_id) for item in before[0]
        ]
        assert [(item.id, item.result_id) for item in after[1]] == [
            (item.id, item.result_id) for item in before[1]
        ]


def test_loader_rejects_evidence_from_another_run(app) -> None:
    rubric = load_rubric(RUBRIC_PATH)
    with app.app_context():
        development_run = _run("development-run", "development")
        holdout_run = _run("holdout-run", "holdout")
        holdout_judge, holdout_human = _evidence(holdout_run, suffix="holdout")
        db.session.commit()

        with pytest.raises(CalibrationError, match="requested run and split"):
            load_calibration_cohort(
                development_run.id,
                ((holdout_judge.id, holdout_human.id),),
                rubric=rubric,
            )


def test_loader_rejects_legacy_mixed_runs(app) -> None:
    rubric = load_rubric(RUBRIC_PATH)
    with app.app_context():
        run = _run("legacy-run", "legacy_mixed")
        judge, human = _evidence(run, suffix="legacy")
        db.session.commit()

        with pytest.raises(CalibrationError, match="development or holdout"):
            load_calibration_cohort(
                run.id,
                ((judge.id, human.id),),
                rubric=rubric,
            )
