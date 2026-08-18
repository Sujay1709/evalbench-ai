from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ScorerSpec(BaseModel):
    type: Literal["exact_match", "json_schema"]
    expected: str | None = None
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    case_sensitive: bool = False

    @model_validator(mode="after")
    def require_scorer_configuration(self) -> "ScorerSpec":
        if self.type == "exact_match" and self.expected is None:
            raise ValueError("exact_match requires 'expected'")
        if self.type == "json_schema" and self.json_schema is None:
            raise ValueError("json_schema requires 'schema'")
        return self


class DatasetProvenance(BaseModel):
    """Identity and license information for one externally sourced example."""

    dataset_id: str = Field(min_length=1)
    config: str = Field(min_length=1)
    split: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    sample_offset: int = Field(ge=0)
    source_url: str = Field(pattern=r"^https://")
    license: str = Field(min_length=1)
    retrieved_at: date


class EvaluationExample(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    input: dict[str, Any]
    mock_response: str
    scorers: list[ScorerSpec] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    split: Literal["development", "holdout"] = "development"
    provenance: DatasetProvenance | None = None
