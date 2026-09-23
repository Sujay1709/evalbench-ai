"""Blind human annotations kept independent from model-judge attempts."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from evalbench.datasets import LoadedDataset
from evalbench.extensions import db
from evalbench.judges.execution import prepare_judgment
from evalbench.judges.rubrics import RubricDefinition
from evalbench.models import ExampleResult, HumanLabelSet


class HumanLabelError(ValueError):
    """The annotation cannot be stored against the selected rubric/result."""


class HumanCriterionRating(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: StrictStr = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    score: StrictInt = Field(ge=0, le=2)
    reason: StrictStr = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A human rating needs a nonblank reason")
        return value.strip()


@dataclass(frozen=True)
class BlindAnnotation:
    result_id: int
    example_id: str
    question: str
    context: str
    reference: str
    response: str
    rubric_hash: str
    presentation_hash: str


def _presentation_hash(
    *, question: str, context: str, reference: str, response: str, rubric_hash: str
) -> str:
    payload = {
        "question": question,
        "context": context,
        "reference": reference,
        "response": response,
        "rubric_hash": rubric_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def prepare_blind_annotation(
    *, run_id: str, example_id: str, dataset: LoadedDataset, rubric: RubricDefinition
) -> BlindAnnotation:
    """Use the judge's identity checks, but never fetch or reveal its verdict."""
    prepared = prepare_judgment(
        run_id=run_id, example_id=example_id, dataset=dataset, rubric=rubric
    )
    return BlindAnnotation(
        result_id=prepared.result_id,
        example_id=example_id,
        question=prepared.question,
        context=prepared.sources["context"],
        reference=prepared.sources["reference"],
        response=prepared.sources["response"],
        rubric_hash=rubric.content_hash,
        presentation_hash=_presentation_hash(
            question=prepared.question,
            context=prepared.sources["context"],
            reference=prepared.sources["reference"],
            response=prepared.sources["response"],
            rubric_hash=rubric.content_hash,
        ),
    )


def record_human_labels(
    presentation: BlindAnnotation,
    *,
    rubric: RubricDefinition,
    annotator_id: str,
    ratings: Sequence[HumanCriterionRating],
) -> HumanLabelSet:
    """Persist one complete rubric pass; re-labels create new rows, never edits."""
    validate_annotator_id(annotator_id)
    if presentation.rubric_hash != rubric.content_hash:
        raise HumanLabelError("Rubric changed since the blind annotation was prepared")
    result = db.session.get(ExampleResult, presentation.result_id)
    if result is None:
        raise HumanLabelError("The evaluation result no longer exists")
    if (
        result.input_json.get("question") != presentation.question
        or result.input_json.get("context") != presentation.context
        or result.output_text != presentation.response
        or presentation.presentation_hash
        != _presentation_hash(
            question=presentation.question,
            context=presentation.context,
            reference=presentation.reference,
            response=presentation.response,
            rubric_hash=presentation.rubric_hash,
        )
    ):
        raise HumanLabelError("Annotation content changed after its presentation was prepared")

    validated = [HumanCriterionRating.model_validate(rating) for rating in ratings]
    expected = [criterion.id for criterion in rubric.criteria]
    actual = [rating.criterion_id for rating in validated]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise HumanLabelError(
            f"Human labels must cover each rubric criterion exactly once: {expected}"
        )
    by_id = {rating.criterion_id: rating for rating in validated}
    label_set = HumanLabelSet(
        id=str(uuid4()),
        result_id=presentation.result_id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        annotator_id=annotator_id,
        presentation_hash=presentation.presentation_hash,
        ratings_json=[by_id[criterion_id].model_dump(mode="json") for criterion_id in expected],
    )
    db.session.add(label_set)
    db.session.commit()
    return label_set


def validate_annotator_id(annotator_id: str) -> None:
    """Require a pseudonym-compatible identifier before collecting ratings."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", annotator_id):
        raise HumanLabelError(
            "Use a 3–64 character pseudonymous annotator ID (letters, digits, _ or -)"
        )
