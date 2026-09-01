import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import inngest
from flask import Flask
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import update

from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.workflows.events import (
    EVALUATION_RUN_REQUESTED_EVENT,
    EvaluationRunRequestedData,
)

FAILURE_EVENT_NAME = "inngest/function.failed"
_CATEGORY_PREFIX = "evalbench_failure:"


class FailureCategory(StrEnum):
    INVALID_REQUEST = "invalid_request"
    CONFIGURATION = "configuration"
    PROVIDER_RESPONSE = "provider_response"
    PROVIDER_RETRIES_EXHAUSTED = "provider_retries_exhausted"
    PERSISTENCE_INTEGRITY = "persistence_integrity"
    WORKFLOW_STATE = "workflow_state"
    INFRASTRUCTURE = "infrastructure"
    UNEXPECTED = "unexpected"


_SAFE_MESSAGES = {
    FailureCategory.INVALID_REQUEST: "The evaluation request failed validation.",
    FailureCategory.CONFIGURATION: "The evaluation configuration is invalid or unavailable.",
    FailureCategory.PROVIDER_RESPONSE: "The provider returned an unusable response.",
    FailureCategory.PROVIDER_RETRIES_EXHAUSTED: (
        "The provider remained unavailable after all retry attempts."
    ),
    FailureCategory.PERSISTENCE_INTEGRITY: (
        "Persisted evaluation data failed an integrity check."
    ),
    FailureCategory.WORKFLOW_STATE: "The durable workflow reached an invalid state.",
    FailureCategory.INFRASTRUCTURE: "Evaluation infrastructure failed after retry attempts.",
    FailureCategory.UNEXPECTED: "The durable evaluation workflow failed unexpectedly.",
}


class SerializedFailureError(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    message: str


class OriginalEvaluationEvent(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    data: EvaluationRunRequestedData


class EvaluationFailureData(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    error: SerializedFailureError
    event: OriginalEvaluationEvent
    function_id: str
    run_id: str

    @field_validator("event", mode="before")
    @classmethod
    def parse_serialized_original_event(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("original failure event is not valid JSON") from exc
        return value


def non_retriable_failure(
    category: FailureCategory,
    message: str,
) -> inngest.NonRetriableError:
    """Tag a safe workflow error so the final handler can retain its category."""

    return inngest.NonRetriableError(f"{_CATEGORY_PREFIX}{category.value}: {message}")


def _parse_failure_data(ctx: inngest.ContextSync) -> EvaluationFailureData:
    if ctx.event.name != FAILURE_EVENT_NAME:
        raise inngest.NonRetriableError(
            f"Failure handler expected '{FAILURE_EVENT_NAME}'"
        )
    try:
        failure = EvaluationFailureData.model_validate(ctx.event.data)
    except ValidationError as exc:
        raise inngest.NonRetriableError(
            "inngest/function.failed contained invalid evaluation metadata"
        ) from exc
    if failure.event.name != EVALUATION_RUN_REQUESTED_EVENT:
        raise inngest.NonRetriableError(
            f"Failure handler cannot process original event '{failure.event.name}'"
        )
    return failure


def _classify_failure(error: SerializedFailureError) -> FailureCategory:
    if error.message.startswith(_CATEGORY_PREFIX):
        category_value = error.message.removeprefix(_CATEGORY_PREFIX).split(":", 1)[0]
        try:
            return FailureCategory(category_value)
        except ValueError:
            return FailureCategory.UNEXPECTED

    if error.name == "ProviderTransientError":
        return FailureCategory.PROVIDER_RETRIES_EXHAUSTED
    if error.name in {"OperationalError", "DatabaseError", "IntegrityError"}:
        return FailureCategory.INFRASTRUCTURE
    return FailureCategory.UNEXPECTED


def finalize_evaluation_failure(
    ctx: inngest.ContextSync,
    app: Flask,
) -> dict[str, str]:
    """Idempotently finalize a run after Inngest exhausts the main function retries."""

    failure = _parse_failure_data(ctx)
    request = failure.event.data
    category = _classify_failure(failure.error)

    with app.app_context():
        run = db.session.get(EvaluationRun, str(request.run_id))
        if run is None:
            raise inngest.NonRetriableError(
                f"Cannot finalize unknown evaluation run '{request.run_id}'"
            )
        if run.correlation_id != str(request.correlation_id):
            raise inngest.NonRetriableError(
                f"Cannot finalize evaluation run '{request.run_id}' with a different "
                "correlation ID"
            )
        if run.status == "completed":
            return {
                "status": "completed_preserved",
                "run_id": run.id,
                "correlation_id": run.correlation_id,
            }
        if run.status == "failed":
            return {
                "status": "already_failed",
                "run_id": run.id,
                "correlation_id": run.correlation_id,
                "error_category": run.error_category or FailureCategory.UNEXPECTED.value,
            }
        if run.status not in {"queued", "running"}:
            raise inngest.NonRetriableError(
                f"Evaluation run '{run.id}' cannot fail from status '{run.status}'"
            )

        persisted_run_id = run.id
        persisted_correlation_id = run.correlation_id
        completed_at = datetime.now(UTC)
        update_result = db.session.execute(
            update(EvaluationRun)
            .where(
                EvaluationRun.id == persisted_run_id,
                EvaluationRun.correlation_id == persisted_correlation_id,
                EvaluationRun.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                error_category=category.value,
                error_message=_SAFE_MESSAGES[category],
                completed_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if update_result.rowcount != 1:
            db.session.rollback()
            current_run = db.session.get(EvaluationRun, persisted_run_id)
            if current_run is not None and current_run.status == "completed":
                return {
                    "status": "completed_preserved",
                    "run_id": current_run.id,
                    "correlation_id": current_run.correlation_id,
                }
            if current_run is not None and current_run.status == "failed":
                return {
                    "status": "already_failed",
                    "run_id": current_run.id,
                    "correlation_id": current_run.correlation_id,
                    "error_category": current_run.error_category
                    or FailureCategory.UNEXPECTED.value,
                }
            raise inngest.NonRetriableError(
                f"Evaluation run '{persisted_run_id}' changed state before failure finalization"
            )

        db.session.commit()
        return {
            "status": "failed",
            "run_id": persisted_run_id,
            "correlation_id": persisted_correlation_id,
            "error_category": category.value,
        }
