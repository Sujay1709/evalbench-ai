import pytest

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import ExampleResult
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider, ProviderResponse
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


@pytest.fixture
def efficiency_runs(app):
    class Degraded(MockProvider):
        name = "degraded-efficiency"

        def generate(self, prompt, example):
            response = super().generate(prompt, example)
            return ProviderResponse("incorrect", 25, response.metadata)

    dataset = load_jsonl(PROJECT_ROOT / "datasets/automotive_qa/v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts/automotive_qa/v1.yaml")
    before = EvaluationRunner(MockProvider()).run(dataset, prompt)
    after = EvaluationRunner(Degraded()).run(dataset, prompt)
    return before.id, after.id


def test_leaderboard_and_pareto_table_are_read_only(client, efficiency_runs):
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert b"Trade-offs, not one winner" in response.data
    assert b"Generation-equivalent cost" in response.data
    assert b"Frontier" in response.data
    assert b"Dominated" in response.data
    assert b"Exact values and frontier membership are listed" in response.data
    assert not db.session.new and not db.session.dirty and not db.session.deleted
    assert client.post("/leaderboard").status_code == 405


def test_comparison_shows_efficiency_delta(client, efficiency_runs):
    response = client.get(
        "/compare",
        query_string={"baseline": efficiency_runs[0], "candidate": efficiency_runs[1]},
    )
    assert response.status_code == 200
    assert b"Quality has an operating cost" in response.data
    assert b"Median generation latency" in response.data
    assert b"Candidate minus baseline generation-equivalent cost" in response.data


def test_historical_unknown_usage_is_not_rendered_as_free(client, efficiency_runs):
    for result in db.session.execute(db.select(ExampleResult)).scalars():
        result.usage_json = None
    db.session.commit()
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert b"No complete cost measurements yet" in response.data
    assert b"Unknown" in response.data


def test_run_detail_explains_cache_and_measurement_basis(client, efficiency_runs):
    response = client.get(f"/runs/{efficiency_runs[0]}")
    assert response.status_code == 200
    assert b"Recorded efficiency" in response.data
    assert b"cached zeros are excluded" in response.data
    assert b"not invoices" in response.data


def test_empty_leaderboard_state(client):
    response = client.get("/leaderboard")
    assert response.status_code == 200
    assert b"No comparable completed runs" in response.data
