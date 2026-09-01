import hashlib
import math
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import inngest
from flask import Flask
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evalbench.config import PROJECT_ROOT, Settings
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult, ResponseCache
from evalbench.providers import (
    Provider,
    ProviderError,
    ProviderTransientError,
    build_provider,
)
from evalbench.runners.aggregation import AggregationError, aggregate_example_scores
from evalbench.runners.generation import generate_or_load_response, response_cache_key
from evalbench.runners.scoring import score_example_output
from evalbench.workflows.artifacts import EvaluationArtifacts, load_run_artifacts
from evalbench.workflows.events import (
    EVALUATION_RUN_REQUESTED_EVENT,
    EvaluationRunRequestedData,
)


class GenerationCheckpoint(BaseModel):
    """Non-sensitive generation metadata passed to the scoring checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_hit: bool
    latency_ms: float = Field(ge=0)


class CompletionCheckpoint(BaseModel):
    """Non-sensitive final metrics returned by the completion checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["completed", "already_completed"]
    run_id: str
    passed_examples: int = Field(ge=0)
    total_examples: int = Field(gt=0)
    mean_score: float = Field(ge=0, le=1)
    completed_at: datetime


def create_workflow_functions(
    client: inngest.Inngest,
    app: Flask,
    settings: Settings | None = None,
) -> list[Any]:
    """Create the functions served by this app-specific Inngest client."""

    configured_settings = settings or Settings()

    function = client.create_function(
        fn_id="eval-run",
        name="Execute evaluation run",
        trigger=inngest.TriggerEvent(event=EVALUATION_RUN_REQUESTED_EVENT),
        idempotency="event.data.run_id",
        retries=2,
    )(
        lambda ctx: execute_evaluation_run(
            ctx,
            app,
            provider_factory=lambda: build_provider(configured_settings),
        )
    )
    return [function]


def _parse_request(ctx: inngest.ContextSync) -> EvaluationRunRequestedData:
    try:
        return EvaluationRunRequestedData.model_validate(ctx.event.data)
    except ValidationError as exc:
        raise inngest.NonRetriableError(
            "eval/run.requested contained invalid identifiers"
        ) from exc


def _validate_persisted_run(
    app: Flask,
    request: EvaluationRunRequestedData,
) -> dict[str, str]:
    with app.app_context():
        run = db.session.get(EvaluationRun, str(request.run_id))
        if run is None:
            raise inngest.NonRetriableError(
                f"Evaluation run '{request.run_id}' does not exist"
            )
        if run.correlation_id != str(request.correlation_id):
            raise inngest.NonRetriableError(
                f"Evaluation run '{request.run_id}' has a different correlation ID"
            )
        if run.status == "failed":
            raise inngest.NonRetriableError(
                f"Evaluation run '{request.run_id}' is already failed"
            )
        if run.status not in {"queued", "running", "completed"}:
            raise inngest.NonRetriableError(
                f"Evaluation run '{request.run_id}' has unsupported status '{run.status}'"
            )

        if run.status == "queued":
            run.status = "running"
            db.session.commit()

        workflow_status = "already_completed" if run.status == "completed" else "ready"
        return {
            "status": workflow_status,
            "run_id": run.id,
            "correlation_id": run.correlation_id,
        }


def validate_evaluation_run_request(
    ctx: inngest.ContextSync,
    app: Flask,
) -> dict[str, str]:
    """Validate a persisted run in a memoized, independently retriable step."""

    request = _parse_request(ctx)

    def validate_step() -> dict[str, str]:
        return _validate_persisted_run(app, request)

    return ctx.step.run("validate-persisted-run", validate_step)


def _load_verified_artifacts(
    app: Flask,
    request: EvaluationRunRequestedData,
    project_root: Path,
) -> tuple[EvaluationRun, EvaluationArtifacts]:
    try:
        with app.app_context():
            run = db.session.get(EvaluationRun, str(request.run_id))
            if run is None:
                raise ValueError(f"Evaluation run '{request.run_id}' does not exist")
            artifacts = load_run_artifacts(run, project_root=project_root)
            return run, artifacts
    except (OSError, ValueError) as exc:
        raise inngest.NonRetriableError(
            f"Evaluation run inputs are invalid: {exc}"
        ) from exc


def _build_verified_provider(
    run: EvaluationRun,
    provider_factory: Callable[[], Provider],
) -> Provider:
    try:
        provider = provider_factory()
    except (ProviderError, ValueError) as exc:
        raise inngest.NonRetriableError(
            f"Evaluation provider configuration is invalid: {exc}"
        ) from exc

    if provider.name != run.provider:
        raise inngest.NonRetriableError(
            f"Configured provider '{provider.name}' does not match evaluation run provider "
            f"'{run.provider}'"
        )
    return provider


def _generation_step_id(example_id: str) -> str:
    digest = hashlib.sha256(example_id.encode()).hexdigest()[:16]
    return f"generate-response-{digest}"


def _scoring_step_id(example_id: str) -> str:
    digest = hashlib.sha256(example_id.encode()).hexdigest()[:16]
    return f"score-response-{digest}"


def _generate_example_response(
    app: Flask,
    provider: Provider,
    artifacts: EvaluationArtifacts,
    example_index: int,
) -> dict[str, str | float | bool]:
    example = artifacts.dataset.examples[example_index]
    try:
        with app.app_context():
            generated = generate_or_load_response(
                provider,
                artifacts.prompt,
                artifacts.dataset.content_hash,
                example,
                commit_cache=True,
            )
    except ProviderTransientError:
        raise
    except (ProviderError, ValueError) as exc:
        raise inngest.NonRetriableError(
            f"Response generation failed for example '{example.id}': {exc}"
        ) from exc

    return {
        "example_id": example.id,
        "cache_key": generated.cache_key,
        "cache_hit": generated.cache_hit,
        "latency_ms": generated.latency_ms,
    }


def _validate_generation_checkpoint(
    value: object,
    *,
    expected_example_id: str,
    expected_cache_key: str,
) -> GenerationCheckpoint:
    try:
        checkpoint = GenerationCheckpoint.model_validate(value)
    except ValidationError as exc:
        raise inngest.NonRetriableError(
            f"Generation checkpoint for example '{expected_example_id}' is invalid"
        ) from exc
    if checkpoint.example_id != expected_example_id:
        raise inngest.NonRetriableError(
            f"Generation checkpoint example '{checkpoint.example_id}' does not match "
            f"'{expected_example_id}'"
        )
    if checkpoint.cache_key != expected_cache_key:
        raise inngest.NonRetriableError(
            f"Generation checkpoint cache key does not match example '{expected_example_id}'"
        )
    return checkpoint


def _score_and_persist_example(
    app: Flask,
    run_id: str,
    artifacts: EvaluationArtifacts,
    example_index: int,
    checkpoint: GenerationCheckpoint,
) -> dict[str, str | float | bool | int]:
    example = artifacts.dataset.examples[example_index]
    with app.app_context():
        cached_response = db.session.get(ResponseCache, checkpoint.cache_key)
        if cached_response is None:
            raise inngest.NonRetriableError(
                f"Generated response cache entry is missing for example '{example.id}'"
            )

        existing_result = db.session.execute(
            db.select(ExampleResult).where(
                ExampleResult.run_id == run_id,
                ExampleResult.example_id == example.id,
            )
        ).scalar_one_or_none()
        if existing_result is not None:
            if (
                existing_result.input_json != example.input
                or existing_result.output_text != cached_response.output_text
            ):
                raise inngest.NonRetriableError(
                    f"Persisted score for example '{example.id}' conflicts with run inputs"
                )
            return {
                "status": "already_scored",
                "example_id": example.id,
                "passed": existing_result.passed,
                "score": existing_result.score,
                "scorer_count": len(existing_result.scorer_details),
            }

        try:
            scored = score_example_output(cached_response.output_text, example)
        except (TypeError, ValueError) as exc:
            raise inngest.NonRetriableError(
                f"Deterministic scoring failed for example '{example.id}': {exc}"
            ) from exc

        db.session.add(
            ExampleResult(
                run_id=run_id,
                example_id=example.id,
                input_json=example.input,
                output_text=cached_response.output_text,
                passed=scored.passed,
                score=scored.score,
                scorer_details=scored.scorer_details,
                cache_hit=checkpoint.cache_hit,
                latency_ms=checkpoint.latency_ms,
            )
        )
        db.session.commit()
        return {
            "status": "scored",
            "example_id": example.id,
            "passed": scored.passed,
            "score": scored.score,
            "scorer_count": len(scored.scorer_details),
        }


def _aggregate_and_complete_run(
    app: Flask,
    run_id: str,
    artifacts: EvaluationArtifacts,
) -> dict[str, str | float | int]:
    expected_ids = {example.id for example in artifacts.dataset.examples}

    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        if run is None:
            raise inngest.NonRetriableError(f"Evaluation run '{run_id}' does not exist")
        if run.status not in {"running", "completed"}:
            raise inngest.NonRetriableError(
                f"Evaluation run '{run_id}' cannot complete from status '{run.status}'"
            )

        results = db.session.execute(
            db.select(ExampleResult)
            .where(ExampleResult.run_id == run_id)
            .order_by(ExampleResult.example_id)
        ).scalars().all()
        actual_id_counts = Counter(result.example_id for result in results)
        actual_ids = set(actual_id_counts)
        missing_ids = sorted(expected_ids - actual_ids)
        unexpected_ids = sorted(actual_ids - expected_ids)
        duplicate_ids = sorted(
            example_id for example_id, count in actual_id_counts.items() if count > 1
        )
        coverage_errors = []
        if missing_ids:
            coverage_errors.append(f"missing results: {', '.join(missing_ids)}")
        if unexpected_ids:
            coverage_errors.append(f"unexpected results: {', '.join(unexpected_ids)}")
        if duplicate_ids:
            coverage_errors.append(f"duplicate results: {', '.join(duplicate_ids)}")
        if coverage_errors:
            raise inngest.NonRetriableError(
                f"Evaluation run '{run_id}' result coverage is invalid; "
                + "; ".join(coverage_errors)
            )

        try:
            metrics = aggregate_example_scores(
                (result.passed, result.score) for result in results
            )
        except AggregationError as exc:
            raise inngest.NonRetriableError(
                f"Evaluation run '{run_id}' metrics are invalid: {exc}"
            ) from exc
        if metrics.total_examples != run.total_examples:
            raise inngest.NonRetriableError(
                f"Evaluation run '{run_id}' expected {run.total_examples} results but found "
                f"{metrics.total_examples}"
            )

        if run.status == "completed":
            if run.completed_at is None:
                raise inngest.NonRetriableError(
                    f"Completed evaluation run '{run_id}' has no completion timestamp"
                )
            if run.passed_examples != metrics.passed_examples or not math.isclose(
                run.mean_score,
                metrics.mean_score,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise inngest.NonRetriableError(
                    f"Completed evaluation run '{run_id}' has conflicting aggregate metrics"
                )
            completion_status = "already_completed"
        else:
            run.passed_examples = metrics.passed_examples
            run.mean_score = metrics.mean_score
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            db.session.commit()
            completion_status = "completed"

        return {
            "status": completion_status,
            "run_id": run.id,
            "passed_examples": run.passed_examples,
            "total_examples": run.total_examples,
            "mean_score": run.mean_score,
            "completed_at": run.completed_at.isoformat(),
        }


def _complete_evaluation_run(
    ctx: inngest.ContextSync,
    app: Flask,
    run_id: str,
    artifacts: EvaluationArtifacts,
) -> CompletionCheckpoint:
    value = ctx.step.run(
        "aggregate-and-complete-run",
        lambda: _aggregate_and_complete_run(app, run_id, artifacts),
    )
    try:
        checkpoint = CompletionCheckpoint.model_validate(value)
    except ValidationError as exc:
        raise inngest.NonRetriableError(
            f"Completion checkpoint for evaluation run '{run_id}' is invalid"
        ) from exc
    if checkpoint.run_id != run_id:
        raise inngest.NonRetriableError(
            f"Completion checkpoint run '{checkpoint.run_id}' does not match '{run_id}'"
        )
    return checkpoint


def execute_evaluation_run(
    ctx: inngest.ContextSync,
    app: Flask,
    *,
    provider_factory: Callable[[], Provider],
    project_root: Path = PROJECT_ROOT,
) -> dict[str, str | float | int]:
    """Execute and atomically complete a durable evaluation run."""

    request = _parse_request(ctx)
    validation = validate_evaluation_run_request(ctx, app)
    if validation["status"] == "already_completed":
        _, artifacts = _load_verified_artifacts(app, request, project_root)
        completion = _complete_evaluation_run(
            ctx,
            app,
            str(request.run_id),
            artifacts,
        )
        return {
            "status": completion.status,
            "run_id": str(request.run_id),
            "generated_examples": 0,
            "scored_examples": 0,
            "passed_examples": completion.passed_examples,
            "mean_score": completion.mean_score,
        }

    run, artifacts = _load_verified_artifacts(app, request, project_root)
    provider = _build_verified_provider(run, provider_factory)

    generation_checkpoints: list[GenerationCheckpoint] = []
    for index, example in enumerate(artifacts.dataset.examples):
        checkpoint_value = ctx.step.run(
            _generation_step_id(example.id),
            lambda example_index=index: _generate_example_response(
                app,
                provider,
                artifacts,
                example_index,
            ),
        )
        generation_checkpoints.append(
            _validate_generation_checkpoint(
                checkpoint_value,
                expected_example_id=example.id,
                expected_cache_key=response_cache_key(
                    provider.name,
                    artifacts.prompt,
                    artifacts.dataset.content_hash,
                    example,
                ),
            )
        )

    for index, (example, checkpoint) in enumerate(
        zip(artifacts.dataset.examples, generation_checkpoints, strict=True)
    ):
        ctx.step.run(
            _scoring_step_id(example.id),
            lambda example_index=index, generation_checkpoint=checkpoint: (
                _score_and_persist_example(
                    app,
                    str(request.run_id),
                    artifacts,
                    example_index,
                    generation_checkpoint,
                )
            ),
        )

    completion = _complete_evaluation_run(
        ctx,
        app,
        str(request.run_id),
        artifacts,
    )
    return {
        "status": completion.status,
        "run_id": str(request.run_id),
        "generated_examples": len(artifacts.dataset.examples),
        "scored_examples": len(artifacts.dataset.examples),
        "passed_examples": completion.passed_examples,
        "mean_score": completion.mean_score,
    }


def validate_event_identifiers(ctx: inngest.ContextSync) -> dict[str, str]:
    """Parse event identifiers without touching persistence."""

    request = _parse_request(ctx)
    return {
        "status": "validated",
        "run_id": str(request.run_id),
        "correlation_id": str(request.correlation_id),
    }
