from uuid import UUID

import inngest
from typer.testing import CliRunner

from evalbench import create_app
from evalbench.cli import cli
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from tests.conftest import PROJECT_ROOT

runner = CliRunner()


def test_cli_exposes_run_subcommand():
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "queue" in result.output
    assert "import-hf" in result.output


def test_cli_run_defaults_to_development_split(tmp_path):
    result = runner.invoke(
        cli,
        [
            "run",
            "--dataset",
            str(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"),
            "--prompt",
            str(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml"),
        ],
        env={"DATABASE_URL": f"sqlite:///{tmp_path / 'development.db'}"},
    )

    assert result.exit_code == 0
    assert "Dataset split: development" in result.output
    assert "auto-004" not in result.output


def test_cli_run_accepts_explicit_holdout_split(tmp_path):
    result = runner.invoke(
        cli,
        [
            "run",
            "--dataset",
            str(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"),
            "--prompt",
            str(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml"),
            "--split",
            "holdout",
        ],
        env={"DATABASE_URL": f"sqlite:///{tmp_path / 'holdout.db'}"},
    )

    assert result.exit_code == 0
    assert "Dataset split: holdout" in result.output
    assert "auto-004" in result.output
    assert "auto-001" not in result.output


def test_cli_queue_prepares_run_and_dispatches_minimal_event(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'queued.db'}"
    captured_events = []

    def capture_event(self, event):
        captured_events.append(event)
        return ["test-event-id"]

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("INNGEST_DEV", "1")
    monkeypatch.setattr(inngest.Inngest, "send_sync", capture_event)

    result = runner.invoke(cli, ["queue", "--split", "development"])

    assert result.exit_code == 0
    assert "Queued EvalBench run" in result.output
    assert "Correlation ID:" in result.output
    assert "Inngest event ID: test-event-id" in result.output
    assert len(captured_events) == 1
    assert captured_events[0].name == "eval/run.requested"
    assert set(captured_events[0].data) == {"run_id", "correlation_id"}
    assert captured_events[0].id == (
        f"eval/run.requested:{captured_events[0].data['run_id']}"
    )

    app = create_app()
    with app.app_context():
        stored_run = db.session.execute(db.select(EvaluationRun)).scalar_one()
        assert stored_run.status == "queued"
        assert stored_run.dataset_split == "development"
        assert stored_run.id == captured_events[0].data["run_id"]
        assert stored_run.correlation_id == captured_events[0].data["correlation_id"]


def test_cli_queue_reuses_run_when_dispatch_is_retried(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'retry.db'}"
    correlation_id = UUID("2f50ae50-84a9-44c6-b008-c9dfb77dcab7")
    dispatch_attempts = 0

    def fail_once(self, event):
        nonlocal dispatch_attempts
        dispatch_attempts += 1
        if dispatch_attempts == 1:
            raise RuntimeError("simulated unavailable Dev Server")
        return ["retried-event-id"]

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("INNGEST_DEV", "1")
    monkeypatch.setattr(inngest.Inngest, "send_sync", fail_once)
    command = ["queue", "--correlation-id", str(correlation_id)]

    failed_dispatch = runner.invoke(cli, command)
    retried_dispatch = runner.invoke(cli, command)

    assert failed_dispatch.exit_code == 1
    assert "remains queued" in failed_dispatch.output
    assert f"--correlation-id {correlation_id}" in " ".join(failed_dispatch.output.split())
    assert retried_dispatch.exit_code == 0
    assert "Inngest event ID: retried-event-id" in retried_dispatch.output
    assert dispatch_attempts == 2

    app = create_app()
    with app.app_context():
        runs = db.session.execute(db.select(EvaluationRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].correlation_id == str(correlation_id)
        assert runs[0].status == "queued"


def test_cli_queue_is_disabled_in_read_only_mode(monkeypatch, tmp_path):
    database_url = f"sqlite:///{tmp_path / 'read-only.db'}"

    def reject_dispatch(self, event):
        raise AssertionError("read-only mode must not dispatch an event")

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DEMO_READ_ONLY", "true")
    monkeypatch.setattr(inngest.Inngest, "send_sync", reject_dispatch)

    result = runner.invoke(cli, ["queue"])

    assert result.exit_code == 1
    assert "durable workflows are disabled in read-only mode" in result.output
    assert not (tmp_path / "read-only.db").exists()
