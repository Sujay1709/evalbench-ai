from datetime import date
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from rich.console import Console
from rich.table import Table
from rich.text import Text

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
from evalbench.judges.execution import (
    JudgePreflightError,
    execute_judgment,
    prepare_judgment,
)
from evalbench.judges.human_labels import (
    HumanCriterionRating,
    HumanLabelError,
    prepare_blind_annotation,
    record_human_labels,
    validate_annotator_id,
)
from evalbench.judges.kev import (
    KevConfigurationError,
    execute_kev_decision,
    prepare_kev_decision,
    validate_local_url,
    validate_pinned_run,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.prompts import load_prompt
from evalbench.providers import build_provider
from evalbench.runners import EvaluationRunner
from evalbench.workflows.events import EvaluationRunRequestedData

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
DEFAULT_PROMPT = PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml"
DEFAULT_RUBRIC = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"

cli = typer.Typer(help="Run reproducible EvalBench experiments.")
console = Console()
error_console = Console(stderr=True)


def prepare_database() -> None:
    """Keep SQLite convenient, but require explicit migrations for hosted storage."""
    if db.engine.dialect.name == "sqlite":
        db.create_all()
        return
    with db.engine.connect() as connection:
        applied_heads = set(MigrationContext.configure(connection).get_current_heads())
    expected_heads = set(ScriptDirectory(str(PROJECT_ROOT / "migrations")).get_heads())
    if applied_heads != expected_heads:
        error_console.print(
            "[red]Database migrations required:[/red] run "
            "flask --app evalbench:create_app db upgrade with your migration role "
            "before running or queuing evaluations."
        )
        raise typer.Exit(code=1)


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
    settings = Settings()
    provider = build_provider(settings)
    app = create_app()
    with app.app_context():
        prepare_database()
        dataset = load_jsonl(dataset_path).select_split(split)
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
        console.print(f"Run ID: {run.id}")
        console.print(
            f"[bold]Pass rate:[/bold] {run.pass_rate:.0%}  "
            f"[bold]Mean score:[/bold] {run.mean_score:.3f}"
        )
        console.print(f"[bold]Dataset split:[/bold] {run.dataset_split}")


@cli.command("queue")
def queue_evaluation(
    dataset_path: Annotated[Path, typer.Option("--dataset")] = DEFAULT_DATASET,
    prompt_path: Annotated[Path, typer.Option("--prompt")] = DEFAULT_PROMPT,
    split: Annotated[
        EvaluationSplit,
        typer.Option("--split", help="Queue one leakage-safe dataset split."),
    ] = EvaluationSplit.DEVELOPMENT,
    correlation_id: Annotated[
        UUID | None,
        typer.Option(
            "--correlation-id",
            help="Reuse this ID to safely retry an uncertain event dispatch.",
        ),
    ] = None,
) -> None:
    """Prepare a durable evaluation and dispatch it through Inngest."""

    settings = Settings()
    app = create_app()
    inngest_client = app.extensions.get("inngest")
    if inngest_client is None:
        error_console.print(
            "[red]Queue unavailable:[/red] durable workflows are disabled in read-only mode.",
        )
        raise typer.Exit(code=1)

    provider = build_provider(settings)
    with app.app_context():
        prepare_database()
        dataset = load_jsonl(dataset_path).select_split(split)
        prompt = load_prompt(prompt_path)
        run = EvaluationRunner(provider).prepare_run(
            dataset,
            prompt,
            correlation_id=correlation_id,
        )
        run_id = run.id
        persisted_correlation_id = run.correlation_id

    event = EvaluationRunRequestedData(
        run_id=UUID(run_id),
        correlation_id=UUID(persisted_correlation_id),
    ).to_inngest_event()
    try:
        event_ids = inngest_client.send_sync(event)
    except Exception as exc:
        error_console.print(
            f"[red]Dispatch failed:[/red] run {run_id} remains queued.\n"
            "Start the Inngest Dev Server and retry with "
            f"--correlation-id {persisted_correlation_id}.",
        )
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Queued EvalBench run {run_id}[/green]")
    console.print(f"Correlation ID: {persisted_correlation_id}")
    console.print(f"Inngest event ID: {', '.join(event_ids)}")
    console.print("Trace: http://localhost:8288")


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
        error_console.print(f"[red]Import failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]Imported {len(result.dataset.examples)} examples[/green] "
        f"to {result.output_path}"
    )
    console.print(f"Dataset hash: {result.dataset.content_hash}")
    console.print(f"Source offsets: {', '.join(map(str, result.source_offsets))}")


@cli.command("judge")
def judge_result(
    run_id: Annotated[str, typer.Option("--run-id", help="Completed evaluation run ID.")],
    example_id: Annotated[str, typer.Option("--example-id", help="One result to judge.")],
    dataset_path: Annotated[Path, typer.Option("--dataset", help="Exact run dataset fixture.")],
    split: Annotated[EvaluationSplit, typer.Option("--split")] = EvaluationSplit.DEVELOPMENT,
    rubric_path: Annotated[Path, typer.Option("--rubric")] = DEFAULT_RUBRIC,
    judge_model: Annotated[str | None, typer.Option("--judge-model")] = None,
    execute: Annotated[
        bool, typer.Option("--execute", help="Authorize exactly one paid judge request.")
    ] = False,
) -> None:
    """Preview one advisory grounded-QA judgment; --execute authorizes the API call."""
    settings = Settings()
    if execute and settings.demo_read_only:
        error_console.print("[red]Judge unavailable:[/red] DEMO_READ_ONLY is enabled")
        raise typer.Exit(code=1)

    app = create_app()
    with app.app_context():
        try:
            prepare_database()
            dataset = load_jsonl(dataset_path).select_split(split)
            rubric = load_rubric(rubric_path)
            prepared = prepare_judgment(
                run_id=run_id, example_id=example_id, dataset=dataset, rubric=rubric
            )
        except (ValueError, OSError) as exc:
            error_console.print(f"[red]Judge preflight failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

        if not execute:
            console.print("[yellow]Dry run:[/yellow] no model request or judge record created")
            console.print(f"Run: {run_id}  Example: {example_id}  Split: {split.value}")
            console.print(
                f"Rubric: {rubric.id}:{rubric.version}  Prompt hash: {prepared.prompt_hash}"
            )
            console.print("Pass --execute --judge-model MODEL to authorize one capped request")
            return

        api_key = settings.openai_api_key
        if api_key is None or not api_key.get_secret_value().strip() or not judge_model:
            error_console.print(
                "[red]Judge configuration missing:[/red] set OPENAI_API_KEY and --judge-model"
            )
            raise typer.Exit(code=1)
        try:
            attempt = execute_judgment(
                prepared,
                rubric=rubric,
                model=judge_model,
                api_key=api_key.get_secret_value(),
                timeout_seconds=settings.openai_timeout_seconds,
            )
        except JudgePreflightError as exc:
            error_console.print(f"[red]Judge preflight failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(f"Judge attempt: {attempt.id}  Status: {attempt.status}")
        if attempt.advisory_score is not None:
            console.print(f"Advisory score: {attempt.advisory_score:.3f}")
        if attempt.error_message:
            error_console.print(attempt.error_message)
        if attempt.status != "completed":
            raise typer.Exit(code=1)


@cli.command("label-human")
def label_human(
    run_id: Annotated[str, typer.Option("--run-id", help="Completed evaluation run ID.")],
    example_id: Annotated[str, typer.Option("--example-id", help="One result to label.")],
    dataset_path: Annotated[Path, typer.Option("--dataset", help="Exact run dataset fixture.")],
    annotator_id: Annotated[
        str, typer.Option("--annotator-id", help="Pseudonymous labeler ID, not an email.")
    ],
    split: Annotated[EvaluationSplit, typer.Option("--split")] = EvaluationSplit.DEVELOPMENT,
    rubric_path: Annotated[Path, typer.Option("--rubric")] = DEFAULT_RUBRIC,
) -> None:
    """Blindly rate one grounded-QA result without seeing the model judge verdict."""
    settings = Settings()
    if settings.demo_read_only:
        error_console.print("[red]Human labeling unavailable:[/red] DEMO_READ_ONLY is enabled")
        raise typer.Exit(code=1)
    try:
        validate_annotator_id(annotator_id)
    except HumanLabelError as exc:
        error_console.print(f"[red]Invalid annotator ID:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    app = create_app()
    with app.app_context():
        try:
            prepare_database()
            dataset = load_jsonl(dataset_path).select_split(split)
            rubric = load_rubric(rubric_path)
            presentation = prepare_blind_annotation(
                run_id=run_id, example_id=example_id, dataset=dataset, rubric=rubric
            )
        except (ValueError, OSError) as exc:
            error_console.print(f"[red]Human label preflight failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

        console.print("Judge verdict and deterministic score are hidden during labeling.")
        for label, value in (
            ("Question", presentation.question),
            ("Context", presentation.context),
            ("Reference", presentation.reference or "(unanswerable; no reference answer)"),
            ("Candidate response", presentation.response),
        ):
            console.print(f"[bold]{label}[/bold]")
            console.print(Text(value))

        ratings = []
        for criterion in rubric.criteria:
            console.print(f"[bold]{criterion.id}[/bold]: {criterion.description}")
            for anchor in criterion.anchors:
                console.print(f"  {anchor.score}: {anchor.description}")
            score = typer.prompt(f"{criterion.id} score (0/1/2)", type=int)
            reason = typer.prompt(f"{criterion.id} reason")
            try:
                ratings.append(
                    HumanCriterionRating(
                        criterion_id=criterion.id, score=score, reason=reason
                    )
                )
            except ValueError as exc:
                error_console.print(f"[red]Invalid human rating:[/red] {exc}")
                raise typer.Exit(code=1) from exc

        try:
            label_set = record_human_labels(
                presentation, rubric=rubric, annotator_id=annotator_id, ratings=ratings
            )
        except HumanLabelError as exc:
            error_console.print(f"[red]Human label not saved:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(f"Saved human label set {label_set.id}")


@cli.command("judge-kev")
def judge_with_kev(
    run_id: Annotated[str, typer.Option("--run-id", help="Completed evaluation run ID.")],
    example_id: Annotated[str, typer.Option("--example-id", help="One result to judge.")],
    dataset_path: Annotated[Path, typer.Option("--dataset", help="Exact run dataset fixture.")],
    expected_run: Annotated[
        str, typer.Option("--expected-run", help="Kev Hub ID pinned to a 40-character commit SHA.")
    ],
    split: Annotated[EvaluationSplit, typer.Option("--split")] = EvaluationSplit.DEVELOPMENT,
    rubric_path: Annotated[Path, typer.Option("--rubric")] = DEFAULT_RUBRIC,
    execute: Annotated[
        bool, typer.Option("--execute", help="Authorize one local Kev inference request.")
    ] = False,
) -> None:
    """Preview or run one local, secondary Kev decision; never change primary scores."""
    settings = Settings()
    if execute and settings.demo_read_only:
        error_console.print("[red]Kev unavailable:[/red] DEMO_READ_ONLY is enabled")
        raise typer.Exit(code=1)
    try:
        validate_pinned_run(expected_run)
        validate_local_url(settings.kev_base_url)
    except KevConfigurationError as exc:
        error_console.print(f"[red]Kev configuration failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    app = create_app()
    with app.app_context():
        try:
            prepare_database()
            dataset = load_jsonl(dataset_path).select_split(split)
            rubric = load_rubric(rubric_path)
            prepared = prepare_judgment(
                run_id=run_id, example_id=example_id, dataset=dataset, rubric=rubric
            )
            kev_request = prepare_kev_decision(prepared, rubric=rubric)
        except (ValueError, OSError) as exc:
            error_console.print(f"[red]Kev preflight failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

        if not execute:
            console.print("[yellow]Dry run:[/yellow] no Kev request or record created")
            console.print(f"Run: {run_id}  Example: {example_id}  Split: {split.value}")
            console.print(f"Pinned checkpoint: {expected_run}")
            console.print(f"Request hash: {kev_request.request_hash}")
            console.print("Pass --execute to authorize one local inference request")
            return

        api_key = settings.kev_api_key
        attempt = execute_kev_decision(
            kev_request,
            rubric=rubric,
            expected_run=expected_run,
            base_url=settings.kev_base_url,
            api_key=api_key.get_secret_value() if api_key else None,
            timeout_seconds=settings.kev_timeout_seconds,
        )
        console.print(f"Kev attempt: {attempt.id}  Status: {attempt.status}")
        if attempt.ratings_json:
            for rating in attempt.ratings_json:
                probabilities = rating["probabilities"]
                console.print(
                    f"{rating['criterion_id']}: expected={rating['expected_score']:.3f}, "
                    f"P(0/1/2)={[probabilities[str(level)] for level in range(3)]}"
                )
        if attempt.error_message:
            error_console.print(attempt.error_message)
        if attempt.status != "completed":
            raise typer.Exit(code=1)


if __name__ == "__main__":
    cli()
