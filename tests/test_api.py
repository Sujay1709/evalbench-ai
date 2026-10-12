"""Read-only JSON API consumed by the React frontend."""

import pytest

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider, ProviderTransientError
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT

RUN_SUMMARY_FIELDS = {
    "id",
    "correlation_id",
    "status",
    "dataset_name",
    "dataset_version",
    "dataset_hash",
    "dataset_split",
    "prompt_id",
    "prompt_version",
    "provider",
    "total_examples",
    "passed_examples",
    "pass_rate",
    "mean_score",
    "created_at",
    "completed_at",
}


def _dataset():
    return load_jsonl(PROJECT_ROOT / "datasets/automotive_qa/v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )


def _prompt():
    return load_prompt(PROJECT_ROOT / "prompts/automotive_qa/v1.yaml")


@pytest.fixture
def completed_run_id(app):
    return EvaluationRunner(MockProvider()).run(_dataset(), _prompt()).id


def test_run_list_is_empty_without_runs(client):
    response = client.get("/api/v1/runs")

    assert response.status_code == 200
    assert response.get_json() == {"runs": []}


def test_run_list_returns_declared_summary_fields(client, completed_run_id):
    response = client.get("/api/v1/runs")

    runs = response.get_json()["runs"]
    assert [run["id"] for run in runs] == [completed_run_id]
    assert set(runs[0]) == RUN_SUMMARY_FIELDS
    assert runs[0]["status"] == "completed"
    assert runs[0]["pass_rate"] == 1.0


@pytest.mark.parametrize("limit", ["0", "201", "ten", "-1"])
def test_run_list_rejects_invalid_limits(client, limit):
    response = client.get("/api/v1/runs", query_string={"limit": limit})

    assert response.status_code == 400
    assert "limit must be an integer" in response.get_json()["error"]


def test_run_detail_includes_results_and_efficiency(client, completed_run_id):
    response = client.get(f"/api/v1/runs/{completed_run_id}")

    payload = response.get_json()
    assert response.status_code == 200
    assert set(payload) == {"run", "failure", "efficiency", "results"}
    assert payload["failure"] is None
    assert payload["efficiency"]["examples"] == 3
    assert len(payload["results"]) == 3
    assert set(payload["results"][0]) == {
        "id",
        "example_id",
        "passed",
        "score",
        "input",
        "output_text",
        "scorer_details",
        "cache_hit",
        "latency_ms",
    }


def test_failed_run_detail_reports_a_safe_failure(client, app):
    class OutageProvider(MockProvider):
        def generate(self, prompt, example):
            raise ProviderTransientError("provider outage")

    with pytest.raises(ProviderTransientError):
        EvaluationRunner(OutageProvider()).run(_dataset(), _prompt())
    run_id = db.session.execute(db.select(EvaluationRun.id)).scalar_one()

    payload = client.get(f"/api/v1/runs/{run_id}").get_json()

    assert payload["run"]["status"] == "failed"
    assert payload["failure"] == {"category": None, "message": "provider outage"}
    assert payload["results"] == []


def test_unknown_run_returns_json_404(client):
    response = client.get("/api/v1/runs/missing")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Evaluation run 'missing' was not found"}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_api_is_read_only(client, completed_run_id, method):
    before = db.session.query(ExampleResult).count()

    response = getattr(client, method)(f"/api/v1/runs/{completed_run_id}")

    assert response.status_code == 405
    assert db.session.query(ExampleResult).count() == before


def test_frontend_is_disabled_by_default(client):
    assert client.get("/app/").status_code == 404


def test_enabled_frontend_without_a_build_explains_how_to_build(client, app, tmp_path):
    app.config.update(FRONTEND_ENABLED=True, FRONTEND_DIST=str(tmp_path / "dist"))

    response = client.get("/app/")

    assert response.status_code == 503
    assert b"npm ci &amp;&amp; npm run build" in response.data


def test_enabled_frontend_serves_assets_and_spa_routes(client, app, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>")
    (dist / "assets" / "app.js").write_text("console.log('ok')")
    app.config.update(FRONTEND_ENABLED=True, FRONTEND_DIST=str(dist))

    asset = client.get("/app/assets/app.js")
    client_route = client.get("/app/runs/some-run")
    traversal = client.get("/app/../evalbench/config.py")

    assert asset.status_code == 200
    assert b"console.log" in asset.data
    assert client_route.status_code == 200
    assert b"id='root'" in client_route.data
    assert b"SECRET_KEY" not in traversal.data
