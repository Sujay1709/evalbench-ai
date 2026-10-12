"""Explicit, versioned response schemas for the read-only frontend API.

The React client depends on these shapes, so fields are declared rather than
derived from ORM columns; adding a column never silently widens the API.
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from evalbench.comparisons.efficiency import EfficiencySummary


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunSummary(_Schema):
    id: str
    correlation_id: str
    status: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    dataset_split: str
    prompt_id: str
    prompt_version: str
    provider: str
    total_examples: int
    passed_examples: int
    pass_rate: float
    mean_score: float
    created_at: datetime
    completed_at: datetime | None


class RunFailure(_Schema):
    category: str | None
    message: str | None


class Efficiency(_Schema):
    examples: int
    cache_hits: int
    generated: int
    median_generation_ms: float | None
    p95_generation_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_generation_cost_usd: float | None
    estimated_new_response_cost_usd: float | None
    cost_coverage: int
    cost_bases: tuple[str, ...]


class ExampleResultView(_Schema):
    id: int
    example_id: str
    passed: bool
    score: float
    input: dict[str, Any]
    output_text: str
    scorer_details: list[dict[str, Any]]
    cache_hit: bool
    latency_ms: float


class RunList(_Schema):
    runs: tuple[RunSummary, ...]


class RunDetail(_Schema):
    run: RunSummary
    failure: RunFailure | None
    efficiency: Efficiency
    results: tuple[ExampleResultView, ...]


class ApiError(_Schema):
    error: str


def run_summary(run) -> RunSummary:
    return RunSummary(
        id=run.id,
        correlation_id=run.correlation_id,
        status=run.status,
        dataset_name=run.dataset_name,
        dataset_version=run.dataset_version,
        dataset_hash=run.dataset_hash,
        dataset_split=run.dataset_split,
        prompt_id=run.prompt_id,
        prompt_version=run.prompt_version,
        provider=run.provider,
        total_examples=run.total_examples,
        passed_examples=run.passed_examples,
        pass_rate=run.pass_rate,
        mean_score=run.mean_score,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def run_detail(run, efficiency: EfficiencySummary) -> RunDetail:
    failure = (
        RunFailure(category=run.error_category, message=run.error_message)
        if run.status == "failed"
        else None
    )
    return RunDetail(
        run=run_summary(run),
        failure=failure,
        efficiency=Efficiency(**asdict(efficiency)),
        results=tuple(
            ExampleResultView(
                id=result.id,
                example_id=result.example_id,
                passed=result.passed,
                score=result.score,
                input=result.input_json,
                output_text=result.output_text,
                scorer_details=result.scorer_details,
                cache_hit=result.cache_hit,
                latency_ms=result.latency_ms,
            )
            for result in run.results
        ),
    )
