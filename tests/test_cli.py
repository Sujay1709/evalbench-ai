from typer.testing import CliRunner

from evalbench.cli import cli
from tests.conftest import PROJECT_ROOT

runner = CliRunner()


def test_cli_exposes_run_subcommand():
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
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
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'development.db'}",
            "LLM_PROVIDER": "mock",
        },
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
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'holdout.db'}",
            "LLM_PROVIDER": "mock",
        },
    )

    assert result.exit_code == 0
    assert "Dataset split: holdout" in result.output
    assert "auto-004" in result.output
    assert "auto-001" not in result.output


def test_cli_run_rejects_missing_split_before_database_init(tmp_path):
    dataset_path = tmp_path / "development_only.jsonl"
    dataset_path.write_text(
        '{"id":"dev-only","input":{"question":"Test?"},'
        '"mock_response":"yes","scorers":[{"type":"exact_match",'
        '"expected":"yes"}],"split":"development"}\n'
    )

    result = runner.invoke(
        cli,
        [
            "run",
            "--dataset",
            str(dataset_path),
            "--prompt",
            str(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml"),
            "--split",
            "holdout",
        ],
        env={
            "DATABASE_URL": f"sqlite:///{tmp_path / 'empty.db'}",
            "LLM_PROVIDER": "mock",
        },
    )

    assert result.exit_code == 1
    assert "contains no 'holdout' examples" in result.output
    assert not (tmp_path / "empty.db").exists()
