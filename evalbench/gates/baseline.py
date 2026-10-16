"""Committed per-example baseline snapshots that a candidate run is gated against."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evalbench.datasets import LoadedDataset
from evalbench.prompts import PromptDefinition


class BaselineError(ValueError):
    """A baseline is missing, malformed, or does not describe the selected benchmark."""


class BaselineExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str = Field(min_length=1)
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    passed: bool


class BaselineSnapshot(BaseModel):
    """Scores, not outputs: the dataset hash already pins every input and scorer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    benchmark: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    dataset_name: str
    dataset_version: str
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_split: Literal["development", "holdout"]
    prompt_id: str
    prompt_version: str
    prompt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    examples: tuple[BaselineExample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_examples(self) -> "BaselineSnapshot":
        ids = [example.example_id for example in self.examples]
        if len(set(ids)) != len(ids):
            raise ValueError("Baseline example IDs must be unique")
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2) + "\n"


@dataclass(frozen=True)
class _BaselineResult:
    example_id: str
    score: float
    passed: bool
    input_json: dict[str, Any]


@dataclass(frozen=True)
class BaselineRun:
    """Satisfies the comparison engine's completed-run protocol."""

    id: str
    status: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    dataset_split: str
    total_examples: int
    passed_examples: int
    mean_score: float
    results: tuple[_BaselineResult, ...]


def snapshot_from_run(run, *, benchmark: str, prompt: PromptDefinition) -> BaselineSnapshot:
    if run.status != "completed":
        raise BaselineError(f"Run '{run.id}' must be completed to record a baseline")
    return BaselineSnapshot(
        benchmark=benchmark,
        provider=run.provider,
        dataset_name=run.dataset_name,
        dataset_version=run.dataset_version,
        dataset_hash=run.dataset_hash,
        dataset_split=run.dataset_split,
        prompt_id=prompt.id,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        examples=tuple(
            BaselineExample(example_id=result.example_id, score=result.score, passed=result.passed)
            for result in sorted(run.results, key=lambda result: result.example_id)
        ),
    )


def load_baseline(path: Path) -> BaselineSnapshot:
    if not path.is_file():
        raise BaselineError(
            f"Baseline not found: {path}. Review the current behavior, then record it with "
            "record-baseline."
        )
    try:
        return BaselineSnapshot.model_validate_json(path.read_text())
    except ValidationError as exc:
        raise BaselineError(f"Invalid baseline {path}: {exc}") from exc


def check_baseline_identity(
    snapshot: BaselineSnapshot, *, benchmark: str, provider: str, dataset: LoadedDataset
) -> None:
    """Refuse comparisons whose difference would come from the benchmark, not the candidate."""
    if snapshot.benchmark != benchmark:
        raise BaselineError(f"Baseline describes '{snapshot.benchmark}', not '{benchmark}'")
    if snapshot.provider != provider:
        raise BaselineError(
            f"Baseline for '{benchmark}' was recorded with provider '{snapshot.provider}', "
            f"but the gate is running '{provider}'"
        )
    if dataset.selected_split is None:
        raise BaselineError("Select a dataset split before comparing against a baseline")
    stored = (
        snapshot.dataset_name,
        snapshot.dataset_version,
        snapshot.dataset_hash,
        snapshot.dataset_split,
    )
    current = (dataset.name, dataset.version, dataset.content_hash, dataset.selected_split.value)
    if stored != current:
        raise BaselineError(
            f"Baseline for '{benchmark}' is stale: its dataset identity or split no longer "
            "matches the configured fixture. Review the dataset change, then refresh it with "
            "record-baseline."
        )


def baseline_run(snapshot: BaselineSnapshot, dataset: LoadedDataset) -> BaselineRun:
    """Present a snapshot as a completed run after its dataset identity was checked."""
    inputs = {example.id: example.input for example in dataset.examples}
    results = tuple(
        _BaselineResult(
            example_id=example.example_id,
            score=example.score,
            passed=example.passed,
            input_json=inputs.get(example.example_id, {}),
        )
        for example in snapshot.examples
    )
    return BaselineRun(
        id=f"baseline:{snapshot.provider}:{snapshot.benchmark}",
        status="completed",
        dataset_name=snapshot.dataset_name,
        dataset_version=snapshot.dataset_version,
        dataset_hash=snapshot.dataset_hash,
        dataset_split=snapshot.dataset_split,
        total_examples=len(results),
        passed_examples=sum(result.passed for result in results),
        mean_score=math.fsum(result.score for result in results) / len(results),
        results=results,
    )
