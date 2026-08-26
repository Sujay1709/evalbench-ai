from typing import Any

import inngest
from pydantic import ValidationError

from evalbench.workflows.events import (
    EVALUATION_RUN_REQUESTED_EVENT,
    EvaluationRunRequestedData,
)


def create_workflow_functions(client: inngest.Inngest) -> list[Any]:
    """Create the functions served by this app-specific Inngest client."""

    function = client.create_function(
        fn_id="eval-run-request-validation",
        name="Validate evaluation run request",
        trigger=inngest.TriggerEvent(event=EVALUATION_RUN_REQUESTED_EVENT),
    )(validate_evaluation_run_request)
    return [function]


def validate_evaluation_run_request(ctx: inngest.Context) -> dict[str, str]:
    try:
        request = EvaluationRunRequestedData.model_validate(ctx.event.data)
    except ValidationError as exc:
        raise inngest.NonRetriableError(
            "eval/run.requested contained invalid identifiers"
        ) from exc

    return {
        "status": "validated",
        "run_id": str(request.run_id),
        "correlation_id": str(request.correlation_id),
    }
