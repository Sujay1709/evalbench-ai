from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from typer.testing import CliRunner

from evalbench.cli import cli
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ResponseCache
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


def migration_config():
    config = Config(str(PROJECT_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return config


def test_postgres_fresh_migration_and_downgrade_round_trip(postgres_app):
    with postgres_app.app_context():
        config = migration_config()
        command.upgrade(config, "head")
        command.check(config)
        assert {"evaluation_runs", "example_results", "response_cache"} <= set(
            inspect(db.engine).get_table_names()
        )
        command.downgrade(config, "base")
        assert inspect(db.engine).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        command.check(config)


def test_postgres_runner_persists_json_usage_timestamps_and_reuses_cache(postgres_app):
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    with postgres_app.app_context():
        command.upgrade(migration_config(), "head")
        runner = EvaluationRunner(MockProvider())
        first = runner.run(dataset, prompt)
        second = runner.run(dataset, prompt)
        assert first.status == second.status == "completed"
        assert first.id != second.id
        assert first.dataset_split == second.dataset_split == "development"
        assert first.total_examples == second.total_examples == 3
        assert first.created_at.utcoffset().total_seconds() == 0
        assert first.completed_at is not None
        assert not any(result.cache_hit for result in first.results)
        assert all(result.cache_hit for result in second.results)
        assert all(isinstance(result.input_json, dict) for result in second.results)
        assert all(result.usage_json["estimated_cost_usd"] == 0.0 for result in second.results)
        assert len(db.session.execute(db.select(ResponseCache)).scalars().all()) == 3
        assert len(db.session.execute(db.select(EvaluationRun)).scalars().all()) == 2

    client = postgres_app.test_client()
    assert client.get("/health/ready").status_code == 200
    assert client.get("/").status_code == 200


def test_postgres_cli_uses_migrations_not_create_all(postgres_app, monkeypatch):
    with postgres_app.app_context():
        command.upgrade(migration_config(), "head")

    monkeypatch.setattr("evalbench.cli.create_app", lambda: postgres_app)

    def reject_implicit_schema_creation():
        raise AssertionError("PostgreSQL runtime must not create tables")

    monkeypatch.setattr(db, "create_all", reject_implicit_schema_creation)
    result = CliRunner().invoke(cli, ["run", "--split", "development"])
    assert result.exit_code == 0, result.output
    assert "Dataset split: development" in result.output


def test_postgres_cli_rejects_unmigrated_database_before_provider_call(postgres_app, monkeypatch):
    monkeypatch.setattr("evalbench.cli.create_app", lambda: postgres_app)

    def reject_generation(*args, **kwargs):
        raise AssertionError("An unmigrated database must not trigger provider calls")

    monkeypatch.setattr(MockProvider, "generate", reject_generation)
    result = CliRunner().invoke(cli, ["run"])
    assert result.exit_code == 1
    assert "Database migrations required" in result.output
    assert "db upgrade" in result.output
    with postgres_app.app_context():
        assert inspect(db.engine).get_table_names() == []
