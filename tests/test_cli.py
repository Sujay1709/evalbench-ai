from typer.testing import CliRunner

from evalbench.cli import cli

runner = CliRunner()


def test_cli_exposes_run_subcommand():
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
