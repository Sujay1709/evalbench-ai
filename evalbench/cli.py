from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from evalbench import create_app
from evalbench.config import Settings
from evalbench.datasets import load_jsonl
from evalbench.extensions import db
from evalbench.prompts import load_prompt
from evalbench.providers import build_provider
from evalbench.runners import EvaluationRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
DEFAULT_PROMPT = PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml"

cli = typer.Typer(help="Run reproducible EvalBench experiments.")
console = Console()


@cli.callback()
def main() -> None:
    """Manage EvalBench evaluation runs."""


@cli.command("run")
def run_evaluation(
    dataset_path: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    prompt_path: Annotated[Path, typer.Option("--prompt")] = DEFAULT_PROMPT,
) -> None:
    """Run a benchmark with the provider selected by environment settings."""
    settings = Settings()
    provider = build_provider(settings)
    app = create_app()
    with app.app_context():
        db.create_all()
        dataset = load_jsonl(dataset_path)
        prompt = load_prompt(prompt_path)
        run = EvaluationRunner(provider).run(dataset, prompt)

        table = Table(title=f"EvalBench run {run.id[:8]}")
        table.add_column("Example")
        table.add_column("Result")
        table.add_column("Score", justify="right")
        table.add_column("Response source")

        for result in run.results:
            table.add_row(
                result.example_id,
                "PASS" if result.passed else "FAIL",
                f"{result.score:.3f}",
                "cache" if result.cache_hit else "generated",
            )

        console.print(table)
        console.print(
            f"[bold]Pass rate:[/bold] {run.pass_rate:.0%}  "
            f"[bold]Mean score:[/bold] {run.mean_score:.3f}"
        )


if __name__ == "__main__":
    cli()
