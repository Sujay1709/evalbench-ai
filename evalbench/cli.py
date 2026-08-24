from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from evalbench import create_app
from evalbench.config import Settings
from evalbench.datasets import (
    EvaluationSplit,
    HuggingFaceDataset,
    HuggingFaceImportError,
    HuggingFaceImportSpec,
    import_huggingface_dataset,
    load_jsonl,
)
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
    split: Annotated[
        EvaluationSplit,
        typer.Option("--split", help="Evaluate one leakage-safe dataset split."),
    ] = EvaluationSplit.DEVELOPMENT,
) -> None:
    """Run a benchmark with the provider selected by environment settings."""
    dataset = load_jsonl(dataset_path).select_split(split)
    prompt = load_prompt(prompt_path)
    settings = Settings()
    provider = build_provider(settings)
    app = create_app()
    with app.app_context():
        db.create_all()
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
        console.print(f"[bold]Dataset split:[/bold] {run.dataset_split}")


@cli.command("import-hf")
def import_huggingface(
    dataset: Annotated[
        HuggingFaceDataset,
        typer.Option("--dataset", help="Supported Hugging Face dataset adapter."),
    ],
    revision: Annotated[
        str,
        typer.Option("--revision", help="Pinned 40-character dataset commit SHA."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", help="Destination EvalBench JSONL file."),
    ],
    source_split: Annotated[str, typer.Option("--source-split")] = "validation",
    target_split: Annotated[
        EvaluationSplit,
        typer.Option("--target-split", help="EvalBench development or holdout split."),
    ] = EvaluationSplit.DEVELOPMENT,
    count: Annotated[int, typer.Option("--count", min=1)] = 10,
    seed: Annotated[int, typer.Option("--seed")] = 42,
    scan_limit: Annotated[int, typer.Option("--scan-limit", min=1)] = 1_000,
    retrieved_at: Annotated[
        str | None,
        typer.Option(
            "--retrieved-at",
            help="Recorded retrieval date in YYYY-MM-DD format; defaults to today.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing output file."),
    ] = False,
) -> None:
    """Stream and normalize a deterministic sample from Hugging Face."""
    try:
        retrieval_date = date.fromisoformat(retrieved_at) if retrieved_at else date.today()
    except ValueError as exc:
        raise typer.BadParameter(
            "must use YYYY-MM-DD format",
            param_hint="--retrieved-at",
        ) from exc

    try:
        spec = HuggingFaceImportSpec(
            dataset=dataset,
            revision=revision,
            output_path=output,
            source_split=source_split,
            target_split=target_split,
            sample_size=count,
            seed=seed,
            scan_limit=scan_limit,
            retrieved_at=retrieval_date,
            force=force,
        )
        result = import_huggingface_dataset(spec)
    except HuggingFaceImportError as exc:
        console.print(f"[red]Import failed:[/red] {exc}", err=True)
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Imported {len(result.dataset.examples)} examples[/green] "
        f"to {result.output_path}"
    )
    console.print(f"Dataset hash: {result.dataset.content_hash}")
    console.print(f"Source offsets: {', '.join(map(str, result.source_offsets))}")


if __name__ == "__main__":
    cli()
