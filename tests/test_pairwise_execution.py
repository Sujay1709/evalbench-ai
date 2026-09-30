"""Offline preflight and persistence checks for pairwise judge execution."""

import json

import pytest
from openai import OpenAIError

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.judges.pairwise import PairwiseJudgment, summarize_order_swaps
from evalbench.judges.pairwise_execution import (
    MAX_PAIRWISE_OUTPUT_TOKENS,
    PairwiseOutputError,
    PairwisePreflightError,
    execute_pairwise_comparison,
    pairwise_response_format,
    parse_pairwise_output,
    prepare_pairwise_comparison,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun, PairwiseJudgeAttempt
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT

DATASET = PROJECT_ROOT / "datasets" / "squad_v2" / "sample_v1.jsonl"
RUBRIC = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"
PROMPT = PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml"
EXAMPLE_ID = "squad-v2-56ddde6b9a695914005b9628"


def _runs(app):
    dataset = load_jsonl(DATASET).select_split(EvaluationSplit.DEVELOPMENT)
    with app.app_context():
        runner = EvaluationRunner(MockProvider())
        run_a = runner.run(dataset, load_prompt(PROMPT))
        run_b = runner.run(dataset, load_prompt(PROMPT))
        return run_a.id, run_b.id, dataset


class FakeResponse:
    def __init__(self, output_text, *, status="completed", response_id="pairwise-response"):
        self.id = response_id
        self.status = status
        self.output_text = output_text
        self.output = []

    def model_dump(self, **kwargs):
        del kwargs
        return {"id": self.id, "status": self.status, "output_text": self.output_text}


class FakePairwiseClient:
    def __init__(self, *, statuses=("completed", "completed"), error_at=None):
        self.responses = self
        self.statuses = iter(statuses)
        self.error_at = error_at
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error_at == len(self.calls):
            raise OpenAIError("secret provider details")
        request = json.loads(kwargs["input"].split("\n", maxsplit=1)[1])
        quote = request["candidate_a"][:40].strip()
        text = json.dumps(
            {
                "preferred_candidate": "A",
                "evidence_source": "candidate_a",
                "evidence_quote": quote,
                "reason": "Candidate A is supported by the cited answer text.",
            }
        )
        return FakeResponse(text, status=next(self.statuses))


@pytest.fixture
def prepared_pair(app):
    run_a_id, run_b_id, dataset = _runs(app)
    rubric = load_rubric(RUBRIC)
    with app.app_context():
        prepared = prepare_pairwise_comparison(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            example_id=EXAMPLE_ID,
            dataset=dataset,
            rubric=rubric,
        )
    return run_a_id, run_b_id, dataset, rubric, prepared


def test_preflight_creates_two_distinct_split_bound_requests_without_writing(app, prepared_pair):
    run_a_id, run_b_id, dataset, rubric, prepared = prepared_pair

    assert prepared.dataset_split == "development"
    assert [request.order_code for request in prepared.requests] == ["ab", "ba"]
    assert prepared.requests[0].presentation_order == tuple(
        reversed(prepared.requests[1].presentation_order)
    )
    assert prepared.requests[0].request_hash != prepared.requests[1].request_hash
    with app.app_context():
        assert db.session.execute(db.select(PairwiseJudgeAttempt)).scalars().all() == []
        assert db.session.get(EvaluationRun, run_a_id).status == "completed"
        assert db.session.get(EvaluationRun, run_b_id).status == "completed"


def test_execute_persists_both_orders_and_exposes_position_flip(app, prepared_pair):
    _, _, _, rubric, prepared = prepared_pair
    client = FakePairwiseClient()
    with app.app_context():
        attempts = execute_pairwise_comparison(
            prepared,
            rubric=rubric,
            model="test-model",
            api_key="fake-key",
            client=client,
        )
        stored = db.session.execute(
            db.select(PairwiseJudgeAttempt)
            .filter_by(comparison_id=prepared.comparison_id)
            .order_by(PairwiseJudgeAttempt.presentation_order)
        ).scalars().all()

    assert len(attempts) == len(stored) == len(client.calls) == 2
    assert {item.presentation_order for item in stored} == {"ab", "ba"}
    assert all(item.status == "completed" for item in stored)
    assert all(item.dataset_split == "development" for item in stored)
    assert all(call["store"] is False for call in client.calls)
    assert all(call["max_output_tokens"] == MAX_PAIRWISE_OUTPUT_TOKENS for call in client.calls)
    evidence = tuple(
        PairwiseJudgment(
            attempt_id=item.id,
            comparison_id=item.comparison_id,
            result_a_id=item.result_a_id,
            result_b_id=item.result_b_id,
            presentation_order=(
                (item.result_a_id, item.result_b_id)
                if item.presentation_order == "ab"
                else (item.result_b_id, item.result_a_id)
            ),
            preferred_result_id=item.preferred_result_id,
            dataset_split=item.dataset_split,
            status=item.status,
            rubric_id=item.rubric_id,
            rubric_version=item.rubric_version,
            rubric_hash=item.rubric_hash,
            judge_model=item.judge_model,
            prompt_version=item.prompt_version,
            prompt_template_hash=item.prompt_template_hash,
        )
        for item in stored
    )
    report = summarize_order_swaps(evidence)
    assert report.preference_flip_rate == 1.0
    assert report.first_position_win_rate == 1.0


def test_failed_orientation_is_recorded_without_leaking_provider_text(app, prepared_pair):
    _, _, _, rubric, prepared = prepared_pair
    client = FakePairwiseClient(error_at=1)
    with app.app_context():
        attempts = execute_pairwise_comparison(
            prepared,
            rubric=rubric,
            model="test-model",
            api_key="fake-key",
            client=client,
        )
        assert [item.status for item in attempts] == ["provider_error", "completed"]
        assert "secret provider details" not in (attempts[0].error_message or "")

    assert len(client.calls) == 2


def test_preflight_rejects_mixed_split_before_any_attempt(app, prepared_pair):
    run_a_id, run_b_id, _, rubric, _ = prepared_pair
    holdout = load_jsonl(DATASET).select_split(EvaluationSplit.HOLDOUT)
    with app.app_context(), pytest.raises(PairwisePreflightError, match="exact same dataset"):
        prepare_pairwise_comparison(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            example_id=EXAMPLE_ID,
            dataset=holdout,
            rubric=rubric,
        )
    assert db.session.execute(db.select(PairwiseJudgeAttempt)).scalars().all() == []


def test_structured_pairwise_output_requires_source_backed_evidence(prepared_pair):
    *_, prepared = prepared_pair
    request = prepared.requests[0]
    assert pairwise_response_format()["strict"] is True
    parsed = parse_pairwise_output(
        json.dumps(
            {
                "preferred_candidate": "A",
                "evidence_source": "candidate_a",
                "evidence_quote": request.sources["candidate_a"][:40].strip(),
                "reason": "The cited text supports this choice.",
            }
        ),
        request=request,
    )
    assert parsed["preferred_result_id"] == request.presentation_order[0]

    invalid = json.dumps(
        {
            "preferred_candidate": "A",
            "evidence_source": "candidate_a",
            "evidence_quote": "not in the source",
            "reason": "This quote is fabricated.",
        }
    )
    with pytest.raises(PairwiseOutputError, match="absent"):
        parse_pairwise_output(invalid, request=request)
