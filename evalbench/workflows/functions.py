from typing import Any

import inngest
from flask import Flask
from pydantic import ValidationError

from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.workflows.events import (
    EVALUATION_RUN_REQUESTED_EVENT,
    EvaluationRunRequestedData,
)


def create_workflow_functions(client: inngest.Inngest, app: Flask) -> list[Any]:
    """Create the functions served by this app-specific Inngest client."""

    function = client.create_function(
        fn_id="eval-run-request-validation",
        name="Validate evaluation run request",
        trigger=inngest.TriggerEvent(event=EVALUATION_RUN_REQUESTED_EVENT),
        idempotency="event.data.run_id",
        retries=2,
    )(lambda ctx: validate_evaluation_run_request(ctx, app))
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


def validate_event_identifiers(ctx: inngest.ContextSync) -> dict[str, str]:
    """Parse event identifiers without touching persistence."""

    request = _parse_request(ctx)
    return {
        "status": "validated",
        "run_id": str(request.run_id),
        "correlation_id": str(request.correlation_id),
    }
