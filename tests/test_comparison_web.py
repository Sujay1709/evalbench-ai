import pytest

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider, ProviderResponse
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


@pytest.fixture
def pair(app):
    class DegradedProvider(MockProvider):
        name = "degraded-web"

        def generate(self, prompt, example):
            return ProviderResponse(text="<script>alert('unsafe')</script>", latency_ms=0)

    dataset = load_jsonl(PROJECT_ROOT / "datasets/automotive_qa/v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts/automotive_qa/v1.yaml")
    baseline = EvaluationRunner(MockProvider()).run(dataset, prompt)
    candidate = EvaluationRunner(DegradedProvider()).run(dataset, prompt)
    return baseline.id, candidate.id


def query(pair, **extra):
    return dict(baseline=pair[0], candidate=pair[1], **extra)


def test_empty_comparison_page(client):
    response = client.get("/compare")
    assert response.status_code == 200
    assert b"No completed runs yet" in response.data


def test_dashboard_reports_evidence_and_remains_read_only(client, app, pair):
    app.config["DEMO_READ_ONLY"] = True
    response = client.get("/compare", query_string=query(pair))
    assert response.status_code == 200
    for text in (b"95% interval", b"Tags", b"Difficulty", b"auto-001", b"newly failing"):
        assert text in response.data
    assert db.session.query(EvaluationRun).count() == 2
    assert not db.session.new and not db.session.dirty and not db.session.deleted
    assert client.post("/compare", data=query(pair)).status_code == 405


def test_drilldown_escapes_provider_output(client, pair):
    response = client.get("/compare/example", query_string=query(pair, example="auto-001"))
    assert response.status_code == 200
    assert b"&lt;script&gt;" in response.data
    assert b"<script>" not in response.data
    assert b"Scorer evidence" in response.data
    assert b"Back to comparison" in response.data


def test_invalid_selections(client, pair):
    assert client.get("/compare", query_string={"baseline": pair[0]}).status_code == 400
    assert client.get("/compare", query_string=query((pair[0], pair[0]))).status_code == 400
    assert client.get("/compare", query_string=query(("missing", pair[1]))).status_code == 404
    assert (
        client.get("/compare/example", query_string=query(pair, example="missing")).status_code
        == 404
    )
    assert client.get("/compare", query_string=query(pair, change="invalid")).status_code == 400


def test_incompatible_runs_have_actionable_errors(client, pair):
    db.session.get(EvaluationRun, pair[1]).dataset_hash = "wrong"
    db.session.commit()
    response = client.get("/compare", query_string=query(pair))
    assert response.status_code == 400
    assert b"different dataset_hash" in response.data
    assert (
        client.get("/compare/example", query_string=query(pair, example="auto-001")).status_code
        == 400
    )


def test_missing_metadata_does_not_hide_paired_results(client, pair, monkeypatch, tmp_path):
    monkeypatch.setattr("evalbench.web.comparison.PROJECT_ROOT", tmp_path)
    response = client.get("/compare", query_string=query(pair))
    assert response.status_code == 200
    assert b"breakdowns unavailable" in response.data
    assert b"auto-001" in response.data


def test_filter_and_navigation(client, pair):
    response = client.get("/compare", query_string=query(pair, change="improved"))
    assert b"No examples match this filter" in response.data
    assert b'aria-current="true"' in response.data
    assert b"Compare runs" in client.get("/").data


def test_registry_traversal_is_rejected(pair):
    from evalbench.web.comparison import load_segments

    baseline, candidate = [db.session.get(EvaluationRun, id) for id in pair]
    baseline.dataset_name = "../outside"
    with pytest.raises(ValueError, match="identity"):
        load_segments(baseline, candidate)


@pytest.mark.parametrize("size", [1, 1001])
def test_dashboard_skips_intervals_outside_request_budget(client, pair, monkeypatch, size):
    from dataclasses import replace

    from evalbench.comparisons import compare_runs

    baseline, candidate = [db.session.get(EvaluationRun, id) for id in pair]
    report = compare_runs(baseline, candidate)
    report = replace(report, examples=(report.examples[0],) * size)
    monkeypatch.setattr("evalbench.web.routes.compare_runs", lambda *args: report)

    def unexpected_call(*args):
        pytest.fail("Bootstrap must not run outside the dashboard budget")

    monkeypatch.setattr("evalbench.web.routes.paired_bootstrap", unexpected_call)
    response = client.get("/compare", query_string=query(pair))
    assert response.status_code == 200
    assert "Dashboard intervals require 2–1,000 pairs" in response.text
