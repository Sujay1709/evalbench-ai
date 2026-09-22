"""Validated, content-addressed rubrics kept separate from evaluation runs."""

import hashlib
import json
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)


def _nonblank_description(value: str) -> str:
    if not value.strip():
        raise ValueError("Rubric descriptions must not be blank")
    return value.strip()


Description = Annotated[StrictStr, AfterValidator(_nonblank_description)]


class RubricAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: StrictInt = Field(ge=0, le=2)
    description: Description


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StrictStr = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    description: Description
    anchors: tuple[RubricAnchor, ...]

    @model_validator(mode="after")
    def require_three_distinct_anchors(self) -> "RubricCriterion":
        if sorted(anchor.score for anchor in self.anchors) != [0, 1, 2]:
            raise ValueError(f"Criterion '{self.id}' needs exactly one anchor each for 0, 1, 2")
        return self


class RubricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: StrictStr = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    version: StrictStr = Field(pattern=r"^v[1-9][0-9]*$", max_length=12)
    description: Description
    criteria: tuple[RubricCriterion, ...] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def require_unique_criteria(self) -> "RubricDefinition":
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Rubric criterion IDs must be unique")
        return self

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_rubric(path: str | Path) -> RubricDefinition:
    rubric_path = Path(path)
    if not rubric_path.is_file():
        raise ValueError(f"Rubric not found: {rubric_path}")
    return RubricDefinition.model_validate(yaml.safe_load(rubric_path.read_text()))
