"""The public demo: idempotent seed, featured regression, readiness, and the read-only guard."""

import html
import re

import pytest
from typer.testing import CliRunner

from evalbench.cli import cli
from evalbench.demo import (
    REGRESSED_KEY,
    REGRESSION_BENCHMARK,
    DemoSeedError,
    demo_ready,
    featured_regression,
    seed_demo,
)
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.providers import MockProvider

WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


class PaidLookingProvider(MockProvider):
    name = "openai"


def run_count():
    return db.session.execute(db.select(db.func.count(EvaluationRun.id))).scalar_one()


def test_seed_is_idempotent_and_never_touches_holdout(app):
    first = seed_demo(MockProvider())
    second = seed_demo(MockProvider())

    assert [item.key for item in first] == [
        "automotive-development",
        "adversarial-development",
        "squad-development",
        "hotpot-development",
        REGRESSED_KEY,
    ]
    assert all(item.created for item in first)
    assert not any(item.created for item in second)
    assert [item.run.id for item in first] == [item.run.id for item in second]
    assert run_count() == 5
    assert {item.run.dataset_split for item in first} == {"development"}
    assert demo_ready()


def test_featured_regression_pairs_the_baseline_with_the_known_bad_prompt(app):
    assert featured_regression() is None
    seed_demo(MockProvider())

    baseline, candidate = featured_regression()

    assert (baseline.prompt_version, candidate.prompt_version) == ("v1", "v1-known-bad")
    assert baseline.dataset_hash == candidate.dataset_hash
    assert (baseline.passed_examples, candidate.passed_examples) == (3, 0)


def test_seed_refuses_any_provider_but_the_offline_mock(app):
    with pytest.raises(DemoSeedError, match="LLM_PROVIDER=mock"):
        seed_demo(PaidLookingProvider())

    assert run_count() == 0


def test_readiness_requires_seeded_demo_data_only_in_demo_mode(app, client):
    app.config["DEMO_READ_ONLY"] = False
    assert client.get("/health/ready").get_json() == {
        "status": "ready",
        "checks": {"database": "ok"},
    }

    app.config["DEMO_READ_ONLY"] = True
    missing = client.get("/health/ready")
    assert missing.status_code == 503
    assert missing.get_json()["checks"] == {"database": "ok", "demo_data": "missing"}

    seed_demo(MockProvider())
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.get_json()["checks"] == {"database": "ok", "demo_data": "ok"}


@pytest.mark.parametrize("method", WRITE_METHODS)
@pytest.mark.parametrize("path", ["/", "/compare", "/health", "/api/inngest", "/no-such-route"])
def test_read_only_demo_rejects_every_write_before_routing(app, client, method, path):
    app.config["DEMO_READ_ONLY"] = True

    response = client.open(path, method=method)

    assert response.status_code == 403
    assert response.get_json()["error"] == "read_only_demo"


def test_reads_stay_open_in_demo_mode_and_writes_route_normally_outside_it(app, client):
    app.config["DEMO_READ_ONLY"] = True
    assert client.get("/").status_code == 200
    assert client.head("/health").status_code == 200

    app.config["DEMO_READ_ONLY"] = False
    assert client.post("/").status_code == 405


def test_every_response_carries_baseline_security_headers(client):
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_home_page_links_a_fresh_visitor_to_the_seeded_regression(app, client):
    assert b"Inspect a caught regression" not in client.get("/").data
    seed_demo(MockProvider())

    page = client.get("/").get_data(as_text=True)
    link = html.unescape(re.search(r'href="(/compare\?[^"]*change=regressed)"', page).group(1))
    report = client.get(link)

    assert "Of 3 automotive examples, 3 passed in the baseline and fail now" in " ".join(
        page.split()
    )
    assert report.status_code == 200
    assert b"3 newly failing" in report.data
    assert b"auto-001" in report.data


def test_demo_seed_cli_is_idempotent_and_refuses_paid_providers(tmp_path):
    runner = CliRunner()
    env = {"DATABASE_URL": f"sqlite:///{tmp_path / 'demo.db'}", "LLM_PROVIDER": "mock"}

    created = runner.invoke(cli, ["demo-seed"], env=env)
    repeated = runner.invoke(cli, ["demo-seed"], env=env)
    refused = runner.invoke(
        cli, ["demo-seed"], env={**env, "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test"}
    )

    assert created.exit_code == 0, created.output
    assert created.output.count("created") == 5
    assert f"{REGRESSION_BENCHMARK}  3/3 passing" in created.output
    assert f"{REGRESSED_KEY}  0/3 passing" in created.output
    assert repeated.exit_code == 0
    assert repeated.output.count("exists") == 5
    assert refused.exit_code == 1
    assert "Demo seed refused" in " ".join(refused.output.split())


def test_demo_seed_cli_reports_an_unopenable_database_without_a_traceback(tmp_path):
    env = {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'missing-dir' / 'demo.db'}",
        "LLM_PROVIDER": "mock",
    }

    result = CliRunner().invoke(cli, ["demo-seed"], env=env)

    assert result.exit_code == 1
    assert "Demo seed failed" in result.output
    assert "Traceback" not in result.output
