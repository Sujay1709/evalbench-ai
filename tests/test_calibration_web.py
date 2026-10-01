"""Browser-facing coverage for the read-only calibration workbench."""

from evalbench.extensions import db
from evalbench.judges.rubrics import load_rubric
from evalbench.models import (
    EvaluationRun,
    ExampleResult,
    HumanLabelSet,
    JudgeAttempt,
    PairwiseJudgeAttempt,
)
from tests.conftest import PROJECT_ROOT

RUBRIC_PATH = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"


def _run(run_id: str, *, dataset_split: str = "development") -> EvaluationRun:
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
    human_score: int,
    judge_score: int,
) -> tuple[ExampleResult, JudgeAttempt, HumanLabelSet]:
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
            {"criterion_id": criterion.id, "score": judge_score} for criterion in rubric.criteria
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
            {"criterion_id": criterion.id, "score": human_score} for criterion in rubric.criteria
        ],
    )
    db.session.add_all((judge, human))
    return result, judge, human


def test_calibration_workbench_exposes_a_read_only_report(app, client):
    with app.app_context():
        run = _run("calibration-run")
        first = _evidence(run, suffix="first", human_score=2, judge_score=2)
        second = _evidence(run, suffix="second", human_score=1, judge_score=2)
        run_id = run.id
        first_result_id, first_judge_id, first_human_id = (
            first[0].id,
            first[1].id,
            first[2].id,
        )
        second_result_id, second_judge_id, second_human_id = (
            second[0].id,
            second[1].id,
            second[2].id,
        )
        db.session.commit()
        before = (
            db.session.execute(db.select(JudgeAttempt)).scalars().all(),
            db.session.execute(db.select(HumanLabelSet)).scalars().all(),
        )

    response = client.get(
        "/calibration",
        query_string={
            "run": run_id,
            f"judge-{first_result_id}": first_judge_id,
            f"human-{first_result_id}": first_human_id,
            f"judge-{second_result_id}": second_judge_id,
            f"human-{second_result_id}": second_human_id,
        },
    )

    assert response.status_code == 200
    assert b"Cohort trace" in response.data
    assert b"Quadratic weighted kappa" in response.data
    assert b"Advisory only" in response.data
    with app.app_context():
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


def test_calibration_workbench_rejects_partial_evidence_selection(app, client):
    with app.app_context():
        run = _run("partial-run")
        result, judge, _ = _evidence(
            run,
            suffix="partial",
            human_score=2,
            judge_score=2,
        )
        run_id = run.id
        result_id = result.id
        judge_id = judge.id
        db.session.commit()

    response = client.get(
        "/calibration",
        query_string={"run": run_id, f"judge-{result_id}": judge_id},
    )

    assert response.status_code == 400
    assert b"Choose both a completed judge attempt and a human label" in response.data
    assert b"Incomplete pair" in response.data


def test_calibration_workbench_hides_legacy_mixed_runs(app, client):
    with app.app_context():
        _run("legacy-run", dataset_split="legacy_mixed")
        db.session.commit()

    index = client.get("/calibration")
    direct_request = client.get("/calibration?run=legacy-run")

    assert index.status_code == 200
    assert b"legacy-run" not in index.data
    assert direct_request.status_code == 404


def test_workbench_summarizes_paired_order_swaps(app, client):
    with app.app_context():
        run = _run("pairwise-workbench-run")
        first, second = (
            _evidence(run, suffix="pairwise-a", human_score=2, judge_score=2),
            _evidence(run, suffix="pairwise-b", human_score=1, judge_score=1),
        )
        first_result_id, second_result_id = first[0].id, second[0].id
        db.session.add_all(
            (
                PairwiseJudgeAttempt(
                    id="pairwise-attempt-ab",
                    comparison_id="pairwise-comparison",
                    result_a_id=first_result_id,
                    result_b_id=second_result_id,
                    preferred_result_id=first_result_id,
                    dataset_split="development",
                    presentation_order="ab",
                    rubric_id="grounded_qa",
                    rubric_version="v1",
                    rubric_hash="d" * 64,
                    prompt_version="v1",
                    prompt_template_hash="e" * 64,
                    request_hash="f" * 64,
                    request_text="A/B request",
                    judge_model="fixture-pairwise-judge",
                    status="completed",
                    choice_json={"preferred_result_id": first_result_id},
                ),
                PairwiseJudgeAttempt(
                    id="pairwise-attempt-ba",
                    comparison_id="pairwise-comparison",
                    result_a_id=first_result_id,
                    result_b_id=second_result_id,
                    preferred_result_id=first_result_id,
                    dataset_split="development",
                    presentation_order="ba",
                    rubric_id="grounded_qa",
                    rubric_version="v1",
                    rubric_hash="d" * 64,
                    prompt_version="v1",
                    prompt_template_hash="e" * 64,
                    request_hash="0" * 64,
                    request_text="B/A request",
                    judge_model="fixture-pairwise-judge",
                    status="completed",
                    choice_json={"preferred_result_id": first_result_id},
                ),
            )
        )
        run_id = run.id
        db.session.commit()

    response = client.get("/calibration", query_string={"run": run_id})

    assert response.status_code == 200
    assert b"Position sensitivity" in response.data
    assert b"0.0% flips" in response.data
    assert b"50.0%" in response.data


def test_readiness_check_requires_holdout_and_reports_selected_thresholds(app, client):
    with app.app_context():
        run = _run("readiness-holdout", dataset_split="holdout")
        evidence = [
            _evidence(
                run,
                suffix=f"readiness-{index}",
                human_score=score,
                judge_score=score,
            )
            for index, score in enumerate((0, 1, 2, 0))
        ]
        query = {
            "run": run.id,
            "gate": "1",
            "minimum_results": "4",
            "minimum_exact_agreement": "0.9",
            "minimum_kappa_lower_bound": "0.8",
        }
        for result, judge, human in evidence:
            query[f"judge-{result.id}"] = judge.id
            query[f"human-{result.id}"] = human.id
        db.session.commit()

    response = client.get("/calibration", query_string=query)

    assert response.status_code == 200
    assert b"Holdout calibration readiness" in response.data
    assert b"Meets selected thresholds" in response.data


def test_readiness_check_rejects_invalid_thresholds(app, client):
    with app.app_context():
        run = _run("readiness-invalid", dataset_split="holdout")
        result, judge, human = _evidence(
            run, suffix="readiness-invalid", human_score=2, judge_score=2
        )
        query = {
            "run": run.id,
            "gate": "1",
            "minimum_results": "1",
            f"judge-{result.id}": judge.id,
            f"human-{result.id}": human.id,
        }
        db.session.commit()

    response = client.get("/calibration", query_string=query)

    assert response.status_code == 400
    assert b"Invalid readiness policy" in response.data
