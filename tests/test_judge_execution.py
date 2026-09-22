"""Offline tests for bounded advisory execution and its append-only evidence."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from openai import OpenAIError

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.judges.execution import (
    MAX_OUTPUT_TOKENS,
    JudgePreflightError,
    execute_judgment,
    prepare_judgment,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun, JudgeAttempt
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT

DATASET = PROJECT_ROOT / "datasets" / "squad_v2" / "sample_v1.jsonl"
RUBRIC = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"
PROMPT = PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml"
EXAMPLE_ID = "squad-v2-56ddde6b9a695914005b9628"


def _run(app):
    dataset = load_jsonl(DATASET).select_split(EvaluationSplit.DEVELOPMENT)
    with app.app_context():
        run = EvaluationRunner(MockProvider()).run(dataset, load_prompt(PROMPT))
        return run.id, dataset


class FakeResponse:
    def __init__(self, *, status="completed", output_text="", output=None):
        self.id = "resp_test"
        self.status = status
        self.output_text = output_text
        self.output = output or []

    def model_dump(self, **kwargs):
        del kwargs
        return {"id": self.id, "status": self.status, "output_text": self.output_text}


class FakeClient:
    def __init__(self, response=None, error=None):
        self.responses = self
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def prepared(app):
    run_id, dataset = _run(app)
    with app.app_context():
        return (
            run_id,
            dataset,
            load_rubric(RUBRIC),
            prepare_judgment(
                run_id=run_id,
                example_id=EXAMPLE_ID,
                dataset=dataset,
                rubric=load_rubric(RUBRIC),
            ),
        )


def _valid_output():
    return (
        '{"assessments":['
        '{"criterion_id":"answer_quality","score":2,"evidence_source":"response",'
        '"evidence_quote":"France","reason":"Correct supported answer"},'
        '{"criterion_id":"evidence_alignment","score":2,"evidence_source":"context",'
        '"evidence_quote":"France","reason":"Context supports this answer"}]}'
    )


def test_success_persists_advisory_evidence_without_mutating_run(app, prepared):
    run_id, _, rubric, selected = prepared
    client = FakeClient(FakeResponse(output_text=_valid_output()))
    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        original = (run.mean_score, run.passed_examples, run.status)
        first = execute_judgment(
            selected, rubric=rubric, model="test-model", api_key="fake", client=client
        )
        second = execute_judgment(
            selected, rubric=rubric, model="test-model", api_key="fake", client=client
        )
        assert first.id != second.id
        assert first.status == "completed"
        assert first.advisory_score == 1.0
        assert first.rubric_hash == rubric.content_hash
        assert first.prompt_hash == selected.prompt_hash
        assert first.response_json["id"] == "resp_test"
        assert len(db.session.execute(db.select(JudgeAttempt)).scalars().all()) == 2
        assert (run.mean_score, run.passed_examples, run.status) == original
    assert len(client.calls) == 2
    assert all(call["store"] is False for call in client.calls)
    assert all(call["max_output_tokens"] == MAX_OUTPUT_TOKENS for call in client.calls)
    assert all(call["text"]["format"]["strict"] is True for call in client.calls)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (FakeResponse(status="incomplete"), "incomplete"),
        (
            FakeResponse(output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])]),
            "refused",
        ),
        (FakeResponse(output_text="not JSON"), "invalid_output"),
    ],
)
def test_non_successful_responses_are_recorded(app, prepared, response, expected):
    _, _, rubric, selected = prepared
    with app.app_context():
        attempt = execute_judgment(
            selected, rubric=rubric, model="test-model", api_key="fake",
            client=FakeClient(response),
        )
        assert attempt.status == expected
        assert attempt.advisory_score is None
        assert attempt.response_json is not None


def test_provider_error_is_recorded_without_sensitive_exception_text(app, prepared):
    _, _, rubric, selected = prepared
    client = FakeClient(error=OpenAIError("secret token in upstream error"))
    with app.app_context():
        attempt = execute_judgment(
            selected, rubric=rubric, model="test-model", api_key="fake", client=client
        )
        assert attempt.status == "provider_error"
        assert "secret token" not in attempt.error_message
        assert attempt.response_json is None
    assert len(client.calls) == 1


def test_preflight_rejects_wrong_split_and_changed_fixture_before_client(app, prepared):
    run_id, dataset, rubric, selected = prepared
    with app.app_context():
        with pytest.raises(JudgePreflightError, match="identity/split"):
            prepare_judgment(
                run_id=run_id, example_id=EXAMPLE_ID,
                dataset=load_jsonl(DATASET).select_split(EvaluationSplit.HOLDOUT),
                rubric=rubric,
            )
        with pytest.raises(JudgePreflightError, match="exact fixture"):
            prepare_judgment(
                run_id=run_id, example_id=EXAMPLE_ID,
                dataset=replace(dataset, content_hash="0" * 64), rubric=rubric,
            )
        assert selected.result_id > 0
        assert db.session.execute(db.select(JudgeAttempt)).scalars().all() == []
