"""Strict judge output boundary; model opinions never replace deterministic scores."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from evalbench.judges.rubrics import RubricDefinition

EvidenceSource = Literal["context", "reference", "response", "none"]


class JudgeOutputError(ValueError):
    """A judge response does not satisfy the pinned rubric/output contract."""


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: StrictStr = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    score: StrictInt = Field(ge=0, le=2)
    evidence_source: EvidenceSource
    evidence_quote: StrictStr = Field(max_length=500)
    reason: StrictStr = Field(min_length=1, max_length=1000)


class _JudgeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assessments: tuple[CriterionAssessment, ...] = Field(min_length=1, max_length=12)


@dataclass(frozen=True)
class JudgeVerdict:
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    example_id: str
    assessments: tuple[CriterionAssessment, ...]

    @property
    def normalized_score(self) -> float:
        """An advisory 0–1 summary; calibration must precede any release gate."""
        return sum(item.score for item in self.assessments) / (2 * len(self.assessments))


def judge_response_format(rubric: RubricDefinition) -> dict:
    """Return a strict Responses API JSON-schema format for this rubric."""
    return {
        "type": "json_schema",
        "name": f"evalbench_{rubric.id}_{rubric.version}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "assessments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "criterion_id": {
                                "type": "string",
                                "enum": [criterion.id for criterion in rubric.criteria],
                            },
                            "score": {"type": "integer", "enum": [0, 1, 2]},
                            "evidence_source": {
                                "type": "string",
                                "enum": ["context", "reference", "response", "none"],
                            },
                            "evidence_quote": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "criterion_id",
                            "score",
                            "evidence_source",
                            "evidence_quote",
                            "reason",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["assessments"],
            "additionalProperties": False,
        },
    }


def parse_judge_output(
    raw: str,
    *,
    rubric: RubricDefinition,
    example_id: str,
    sources: Mapping[str, str],
) -> JudgeVerdict:
    """Validate model JSON, criterion coverage, and exact source-backed quotes."""
    if not example_id.strip():
        raise JudgeOutputError("Judge example_id must not be blank")
    try:
        response = _JudgeResponse.model_validate_json(raw)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        raise JudgeOutputError(f"Invalid judge JSON or fields: {fields}") from exc

    expected = {criterion.id for criterion in rubric.criteria}
    found = [item.criterion_id for item in response.assessments]
    if len(found) != len(set(found)) or set(found) != expected:
        raise JudgeOutputError(
            f"Judge assessments must contain each rubric criterion exactly once; "
            f"expected {sorted(expected)}, received {found}"
        )

    for item in response.assessments:
        quote = item.evidence_quote.strip()
        if not item.reason.strip():
            raise JudgeOutputError(f"Criterion '{item.criterion_id}' needs a nonblank reason")
        if item.evidence_source == "none":
            if quote:
                raise JudgeOutputError(
                    f"Criterion '{item.criterion_id}' cannot quote evidence_source='none'"
                )
            if item.score > 0:
                raise JudgeOutputError(
                    f"Criterion '{item.criterion_id}' needs cited text for a positive score"
                )
            continue
        source_text = sources.get(item.evidence_source)
        if not isinstance(source_text, str) or not quote or quote not in source_text:
            raise JudgeOutputError(
                f"Criterion '{item.criterion_id}' has a quote absent from "
                f"the supplied {item.evidence_source} text"
            )

    return JudgeVerdict(
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        example_id=example_id,
        assessments=response.assessments,
    )
