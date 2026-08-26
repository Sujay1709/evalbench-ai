from uuid import uuid4

import pytest
from pydantic import ValidationError

from evalbench.workflows import EVALUATION_RUN_REQUESTED_EVENT, EvaluationRunRequestedData


def test_evaluation_run_requested_builds_a_minimal_inngest_event():
    run_id = uuid4()
    correlation_id = uuid4()

    event = EvaluationRunRequestedData(
        run_id=run_id,
        correlation_id=correlation_id,
    ).to_inngest_event()

    assert event.name == "eval/run.requested"
    assert event.name == EVALUATION_RUN_REQUESTED_EVENT
    assert event.id == f"eval/run.requested:{run_id}"
    assert event.data == {
        "run_id": str(run_id),
        "correlation_id": str(correlation_id),
    }


@pytest.mark.parametrize("field", ["run_id", "correlation_id"])
def test_evaluation_run_requested_rejects_invalid_identifiers(field):
    payload = {
        "run_id": str(uuid4()),
        "correlation_id": str(uuid4()),
    }
    payload[field] = "not-a-uuid"

    with pytest.raises(ValidationError, match=field):
        EvaluationRunRequestedData.model_validate(payload)


def test_evaluation_run_requested_rejects_unexpected_or_sensitive_data():
    with pytest.raises(ValidationError, match="api_key"):
        EvaluationRunRequestedData.model_validate(
            {
                "run_id": str(uuid4()),
                "correlation_id": str(uuid4()),
                "api_key": "must-not-enter-an-event",
            }
        )
