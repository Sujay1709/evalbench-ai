"""Offline tests for the opt-in, loopback-only secondary Kev decision model."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from evalbench import create_app
from evalbench.cli import cli
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.judges.execution import prepare_judgment
from evalbench.judges.kev import (
    KevConfigurationError,
    execute_kev_decision,
    prepare_kev_decision,
    validate_local_url,
    validate_pinned_run,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun, HumanLabelSet, JudgeAttempt, KevDecisionAttempt
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT

DATASET_PATH = PROJECT_ROOT / "datasets" / "squad_v2" / "sample_v1.jsonl"
RUBRIC_PATH = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml"
EXAMPLE_ID = "squad-v2-56ddde6b9a695914005b9628"
PINNED_RUN = "jaredpalmer/kev-4b@" + "a" * 40


def _seed():
    dataset = load_jsonl(DATASET_PATH).select_split(EvaluationSplit.DEVELOPMENT)
    run = EvaluationRunner(MockProvider()).run(dataset, load_prompt(PROMPT_PATH))
    rubric = load_rubric(RUBRIC_PATH)
    prepared = prepare_judgment(
        run_id=run.id, example_id=EXAMPLE_ID, dataset=dataset, rubric=rubric
    )
    return run.id, rubric, prepare_kev_decision(prepared, rubric=rubric)


def _model_card(run=PINNED_RUN):
    return {
        "models": [
            {
                "name": "kev-latest", "run": run, "temperature": 2.14,
                "base": "Qwen/Qwen3.5-4B-Base", "backend": "mlx", "dtype": "bf16",
            }
        ]
    }


def _decision(rubric):
    answers = {}
    for criterion in rubric.criteria:
        anchors = sorted(criterion.anchors, key=lambda anchor: anchor.score)
        answers[criterion.id] = {
            "type": "score",
            "score": 1.6,
            "legend": {str(anchor.score): anchor.description for anchor in anchors},
            "probabilities": {"0": 0.1, "1": 0.2, "2": 0.7},
            "confidence": 0.75,
        }
    return {"model": "kev-latest", "answers": answers, "usage": {"input_tokens": 100}}


def _transport(rubric, *, card_run=PINNED_RUN, decision=None, calls=None):
    recorded = calls if calls is not None else []

    def handler(request):
        recorded.append(request)
        assert request.url.host == "127.0.0.1"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=_model_card(card_run))
        assert request.url.path == "/v1/systemone"
        return httpx.Response(
            200, json=decision if decision is not None else _decision(rubric),
            headers={"x-typesafe-request-id": "kev-request-123"},
        )

    return httpx.MockTransport(handler)


def test_kev_persists_probabilities_without_mutating_primary_scores(app):
    with app.app_context():
        run_id, rubric, prepared = _seed()
        run = db.session.get(EvaluationRun, run_id)
        before = (run.mean_score, run.passed_examples, run.status)
        calls = []
        first = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            transport=_transport(rubric, calls=calls),
        )
        second = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            transport=_transport(rubric),
        )
        assert first.id != second.id
        assert first.status == "completed"
        assert first.request_hash == prepared.request_hash
        assert first.model_card_json["run"] == PINNED_RUN
        assert first.request_id == "kev-request-123"
        assert [item["expected_score"] for item in first.ratings_json] == [1.6, 1.6]
        assert [item["modal_score"] for item in first.ratings_json] == [2, 2]
        assert len(db.session.execute(db.select(KevDecisionAttempt)).scalars().all()) == 2
        assert db.session.execute(db.select(JudgeAttempt)).scalars().all() == []
        assert db.session.execute(db.select(HumanLabelSet)).scalars().all() == []
        assert (run.mean_score, run.passed_examples, run.status) == before
    assert [request.url.path for request in calls] == ["/v1/models", "/v1/systemone"]
    sent = json.loads(calls[1].content)
    assert sent["model"] == "kev-latest"
    assert sent["state"]["candidate_response"] == "France"
    assert set(sent["questions"]) == {"answer_quality", "evidence_alignment"}
    assert all(question["type"] == "score" for question in sent["questions"].values())


def test_checkpoint_mismatch_is_recorded_without_inference(app):
    with app.app_context():
        _, rubric, prepared = _seed()
        calls = []
        attempt = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            transport=_transport(rubric, card_run="jaredpalmer/kev-4b@" + "b" * 40, calls=calls),
        )
        assert attempt.status == "identity_mismatch"
        assert attempt.ratings_json is None
        assert len(calls) == 1


def test_malformed_probabilities_are_recorded_as_invalid_output(app):
    with app.app_context():
        _, rubric, prepared = _seed()
        response = _decision(rubric)
        response["answers"][rubric.criteria[0].id]["probabilities"] = {
            "0": 0.9, "1": 0.9, "2": 0.9
        }
        attempt = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            transport=_transport(rubric, decision=response),
        )
        assert attempt.status == "invalid_output"
        assert attempt.response_json == response
        assert attempt.ratings_json is None


def test_connection_failure_is_recorded_without_secret_text(app):
    with app.app_context():
        _, rubric, prepared = _seed()

        def fail(request):
            raise httpx.ConnectError("sensitive detail", request=request)

        attempt = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            api_key="local-secret", transport=httpx.MockTransport(fail),
        )
        assert attempt.status == "provider_error"
        assert "sensitive detail" not in attempt.error_message
        assert "local-secret" not in str(attempt.request_json)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8009", "http://localhost:8009", "http://10.0.0.1:8009",
        "http://127.0.0.1:8009/other", "http://user:pass@127.0.0.1:8009",
        "http://127.0.0.1:bad", "http://127.0.0.1:0",
        "http://127.0.0.1:8009?query=1", "http://[::1",
    ],
)
def test_kev_rejects_non_loopback_or_ambiguous_urls(url):
    with pytest.raises(KevConfigurationError, match="KEV_BASE_URL"):
        validate_local_url(url)


def test_kev_requires_immutable_hub_commit():
    with pytest.raises(KevConfigurationError, match="commit SHA"):
        validate_pinned_run("jaredpalmer/kev-4b")
    assert validate_pinned_run(PINNED_RUN) == PINNED_RUN


def test_tampered_request_fails_before_any_network_or_record(app):
    with app.app_context():
        _, rubric, prepared = _seed()
        prepared.payload["state"]["candidate_response"] = "changed after hash"
        with pytest.raises(KevConfigurationError, match="request changed"):
            execute_kev_decision(
                prepared, rubric=rubric, expected_run=PINNED_RUN,
                transport=_transport(rubric),
            )
        assert db.session.execute(db.select(KevDecisionAttempt)).scalars().all() == []


def test_local_server_redirect_is_not_followed(app):
    with app.app_context():
        _, rubric, prepared = _seed()
        calls = []

        def redirect(request):
            calls.append(request)
            return httpx.Response(302, headers={"location": "https://example.com/receive"})

        attempt = execute_kev_decision(
            prepared, rubric=rubric, expected_run=PINNED_RUN,
            transport=httpx.MockTransport(redirect),
        )
        assert attempt.status == "provider_error"
        assert len(calls) == 1
        assert calls[0].url.host == "127.0.0.1"


def test_cli_dry_run_never_calls_kev(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'kev-cli.db'}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DEMO_READ_ONLY", "false")
    app = create_app()
    with app.app_context():
        db.create_all()
        run_id, _, _ = _seed()

    def reject(*args, **kwargs):
        raise AssertionError("Dry run must not contact Kev")

    monkeypatch.setattr("evalbench.cli.execute_kev_decision", reject)
    command = [
        "judge-kev", "--run-id", run_id, "--example-id", EXAMPLE_ID,
        "--dataset", str(DATASET_PATH), "--expected-run", PINNED_RUN,
    ]
    preview = CliRunner().invoke(cli, command)
    assert preview.exit_code == 0
    assert "Dry run" in preview.output
    with app.app_context():
        assert db.session.execute(db.select(KevDecisionAttempt)).scalars().all() == []


def test_cli_execute_uses_mocked_local_kev_server(monkeypatch, tmp_path):
    from evalbench.judges.kev import execute_kev_decision as actual_execute

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'kev-execute.db'}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DEMO_READ_ONLY", "false")
    app = create_app()
    with app.app_context():
        db.create_all()
        run_id, rubric, _ = _seed()
    calls = []

    def mocked_execute(*args, **kwargs):
        kwargs["transport"] = _transport(rubric, calls=calls)
        return actual_execute(*args, **kwargs)

    monkeypatch.setattr("evalbench.cli.execute_kev_decision", mocked_execute)
    result = CliRunner().invoke(
        cli,
        [
            "judge-kev", "--run-id", run_id, "--example-id", EXAMPLE_ID,
            "--dataset", str(DATASET_PATH), "--expected-run", PINNED_RUN, "--execute",
        ],
    )
    assert result.exit_code == 0
    assert "Status: completed" in result.output
    assert "answer_quality: expected=1.600" in result.output
    assert len(calls) == 2
    with app.app_context():
        assert db.session.execute(db.select(KevDecisionAttempt)).scalar_one().status == "completed"


def test_cli_read_only_mode_blocks_kev_before_database_creation(monkeypatch, tmp_path):
    database_path = tmp_path / "kev-read-only.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("DEMO_READ_ONLY", "true")
    result = CliRunner().invoke(
        cli,
        [
            "judge-kev", "--run-id", "unused", "--example-id", EXAMPLE_ID,
            "--dataset", str(DATASET_PATH), "--expected-run", PINNED_RUN, "--execute",
        ],
    )
    assert result.exit_code == 1
    assert "DEMO_READ_ONLY" in result.output
    assert not database_path.exists()
