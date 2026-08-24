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
