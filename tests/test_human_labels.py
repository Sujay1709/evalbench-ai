"""Offline acceptance checks for independent, blind human annotations."""

from dataclasses import replace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from evalbench import create_app
from evalbench.cli import cli
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.judges.execution import JudgePreflightError
from evalbench.judges.human_labels import (
    HumanCriterionRating,
    HumanLabelError,
    prepare_blind_annotation,
    record_human_labels,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun, HumanLabelSet, JudgeAttempt
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT

DATASET_PATH = PROJECT_ROOT / "datasets" / "squad_v2" / "sample_v1.jsonl"
RUBRIC_PATH = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml"
EXAMPLE_ID = "squad-v2-56ddde6b9a695914005b9628"


def _seed_run():
    dataset = load_jsonl(DATASET_PATH).select_split(EvaluationSplit.DEVELOPMENT)
    run = EvaluationRunner(MockProvider()).run(dataset, load_prompt(PROMPT_PATH))
    return run, dataset


def _ratings():
    return [
        HumanCriterionRating(
            criterion_id="answer_quality", score=2, reason="Answers the question"
        ),
        HumanCriterionRating(
            criterion_id="evidence_alignment", score=2, reason="Supported by context"
        ),
    ]


@pytest.fixture
def annotation(app):
    with app.app_context():
        run, dataset = _seed_run()
        rubric = load_rubric(RUBRIC_PATH)
        presentation = prepare_blind_annotation(
            run_id=run.id, example_id=EXAMPLE_ID, dataset=dataset, rubric=rubric
        )
        return run.id, dataset, rubric, presentation


def test_human_labels_are_independent_append_only_and_content_bound(app, annotation):
    run_id, _, rubric, presentation = annotation
    assert "judge" not in vars(presentation)
    assert presentation.question == "In what country is Normandy located?"
    assert presentation.response == "France"
    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        original = (run.mean_score, run.passed_examples, run.status)
        first = record_human_labels(
            presentation, rubric=rubric, annotator_id="labeler_01", ratings=_ratings()
        )
        second = record_human_labels(
            presentation, rubric=rubric, annotator_id="labeler_01", ratings=_ratings()
        )
        assert first.id != second.id
        assert first.result_id == presentation.result_id
        assert first.rubric_hash == rubric.content_hash
        assert first.presentation_hash == presentation.presentation_hash
        assert first.ratings_json == [rating.model_dump(mode="json") for rating in _ratings()]
        assert len(db.session.execute(db.select(HumanLabelSet)).scalars().all()) == 2
        assert db.session.execute(db.select(JudgeAttempt)).scalars().all() == []
        assert (run.mean_score, run.passed_examples, run.status) == original


def test_invalid_or_incomplete_human_labels_are_not_persisted(app, annotation):
    _, _, rubric, presentation = annotation
    with app.app_context():
        with pytest.raises(HumanLabelError, match="exactly once"):
            record_human_labels(
                presentation, rubric=rubric, annotator_id="labeler_01",
                ratings=[_ratings()[0]],
            )
        with pytest.raises(HumanLabelError, match="exactly once"):
            record_human_labels(
                presentation, rubric=rubric, annotator_id="labeler_01",
                ratings=[_ratings()[0], _ratings()[0]],
            )
        with pytest.raises(HumanLabelError, match="pseudonymous"):
            record_human_labels(
                presentation, rubric=rubric, annotator_id="person@example.com",
                ratings=_ratings(),
            )
        with pytest.raises(HumanLabelError, match="Rubric changed"):
            record_human_labels(
                replace(presentation, rubric_hash="0" * 64), rubric=rubric,
                annotator_id="labeler_01", ratings=_ratings(),
            )
        with pytest.raises(HumanLabelError, match="content changed"):
            record_human_labels(
                replace(presentation, response="changed"), rubric=rubric,
                annotator_id="labeler_01", ratings=_ratings(),
            )
        assert db.session.execute(db.select(HumanLabelSet)).scalars().all() == []

    with pytest.raises(ValidationError):
        HumanCriterionRating(criterion_id="answer_quality", score=3, reason="Invalid")
    with pytest.raises(ValidationError):
        HumanCriterionRating(criterion_id="answer_quality", score=2, reason="   ")


def test_preflight_requires_exact_run_split_and_dataset(app, annotation):
    run_id, dataset, rubric, _ = annotation
    with app.app_context():
        with pytest.raises(JudgePreflightError, match="identity/split"):
            prepare_blind_annotation(
                run_id=run_id, example_id=EXAMPLE_ID,
                dataset=load_jsonl(DATASET_PATH).select_split(EvaluationSplit.HOLDOUT),
                rubric=rubric,
            )
        with pytest.raises(JudgePreflightError, match="exact fixture"):
            prepare_blind_annotation(
                run_id=run_id, example_id=EXAMPLE_ID,
                dataset=replace(dataset, content_hash="0" * 64), rubric=rubric,
            )


def test_cli_label_human_hides_judge_verdict_and_saves_label(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'human-label.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DEMO_READ_ONLY", "false")
    app = create_app()
    with app.app_context():
        db.create_all()
        run, _ = _seed_run()
        run_id = run.id
        result = next(item for item in run.results if item.example_id == EXAMPLE_ID)
        db.session.add(
            JudgeAttempt(
                id="existing-judge-attempt", result_id=result.id,
                rubric_id="grounded_qa", rubric_version="v1", rubric_hash="a" * 64,
                prompt_version="v1", prompt_hash="b" * 64, request_text="hidden",
                judge_model="test-model", status="completed",
                response_json={"sentinel": "JUDGE_VERDICT_MUST_STAY_HIDDEN"},
            )
        )
        db.session.commit()

    command = [
        "label-human", "--run-id", run_id, "--example-id", EXAMPLE_ID,
        "--dataset", str(DATASET_PATH), "--annotator-id", "labeler_01",
    ]
    response = CliRunner().invoke(cli, command, input="2\nCorrect answer\n2\nContext supports it\n")
    assert response.exit_code == 0
    assert "Saved human label set" in response.output
    assert "JUDGE_VERDICT_MUST_STAY_HIDDEN" not in response.output
    assert "Judge verdict and deterministic score are hidden" in response.output
    with app.app_context():
        stored = db.session.execute(db.select(HumanLabelSet)).scalar_one()
        assert stored.annotator_id == "labeler_01"
        assert [item["score"] for item in stored.ratings_json] == [2, 2]


def test_cli_label_human_rejects_read_only_without_creating_database(monkeypatch, tmp_path):
    database_path = tmp_path / "read-only.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DEMO_READ_ONLY", "true")
    response = CliRunner().invoke(
        cli,
        [
            "label-human", "--run-id", "irrelevant", "--example-id", EXAMPLE_ID,
            "--dataset", str(DATASET_PATH), "--annotator-id", "labeler_01",
        ],
    )
    assert response.exit_code == 1
    assert "DEMO_READ_ONLY" in response.output
    assert not database_path.exists()


def test_cli_rejects_personal_annotator_id_before_prompting(monkeypatch, tmp_path):
    database_path = tmp_path / "bad-annotator.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DEMO_READ_ONLY", "false")
    response = CliRunner().invoke(
        cli,
        [
            "label-human", "--run-id", "irrelevant", "--example-id", EXAMPLE_ID,
            "--dataset", str(DATASET_PATH), "--annotator-id", "person@example.com",
        ],
    )
    assert response.exit_code == 1
    assert "Invalid annotator ID" in response.output
    assert not database_path.exists()
