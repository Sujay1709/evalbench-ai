from uuid import UUID

import inngest
from pydantic import BaseModel, ConfigDict

EVALUATION_RUN_REQUESTED_EVENT = "eval/run.requested"


class EvaluationRunRequestedData(BaseModel):
    """Identifiers required to execute and trace one persisted evaluation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    correlation_id: UUID

    def to_inngest_event(self) -> inngest.Event:
        return inngest.Event(
            id=f"{EVALUATION_RUN_REQUESTED_EVENT}:{self.run_id}",
            name=EVALUATION_RUN_REQUESTED_EVENT,
            data=self.model_dump(mode="json"),
        )
