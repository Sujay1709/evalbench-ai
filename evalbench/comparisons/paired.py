import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, Protocol


class ComparisonError(ValueError):
    """The stored runs cannot support a trustworthy paired comparison."""


class ExampleOutcome(Protocol):
    example_id: str
    score: float
    passed: bool
    input_json: dict[str, Any]


class CompletedRun(Protocol):
    id: str
    status: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    dataset_split: str
    total_examples: int
    passed_examples: int
    mean_score: float
    results: Iterable[ExampleOutcome]


@dataclass(frozen=True)
class ExampleComparison:
    example_id: str
    baseline_score: float
    candidate_score: float
    score_delta: float
    baseline_passed: bool
    candidate_passed: bool
    change: Literal["improved", "regressed", "unchanged"]


@dataclass(frozen=True)
class RunComparison:
    baseline_run_id: str
    candidate_run_id: str
    dataset_hash: str
    dataset_split: str
    examples: tuple[ExampleComparison, ...]
    baseline_mean_score: float
    candidate_mean_score: float
    mean_score_delta: float
    baseline_pass_rate: float
    candidate_pass_rate: float
    pass_rate_delta: float
    improved: int
    regressed: int
    unchanged: int
    newly_passing: int
    newly_failing: int


def _validated_results(run: CompletedRun) -> dict[str, ExampleOutcome]:
    if run.status != "completed":
        raise ComparisonError(f"Run '{run.id}' must be completed; got '{run.status}'")
    if run.dataset_split not in {"development", "holdout"}:
        raise ComparisonError(f"Run '{run.id}' requires a development or holdout split")
    results: dict[str, ExampleOutcome] = {}
    for result in run.results:
        if not result.example_id or result.example_id in results:
            raise ComparisonError(f"Run '{run.id}' has an empty or duplicate example ID")
        if (
            isinstance(result.score, bool)
            or not isinstance(result.score, (int, float))
            or not math.isfinite(result.score)
            or not 0 <= result.score <= 1
        ):
            raise ComparisonError(
                f"Example '{result.example_id}' requires a finite score in [0, 1]"
            )
        if not isinstance(result.passed, bool):
            raise ComparisonError(f"Example '{result.example_id}' requires a boolean pass outcome")
        results[result.example_id] = result
    if not results or len(results) != run.total_examples:
        raise ComparisonError(f"Run '{run.id}' has incomplete result coverage")
    mean = math.fsum(result.score for result in results.values()) / len(results)
    if run.passed_examples != sum(result.passed for result in results.values()) or not math.isclose(
        run.mean_score, mean, rel_tol=0, abs_tol=1e-12
    ):
        raise ComparisonError(f"Run '{run.id}' has aggregate metrics inconsistent with its results")
    return results


def compare_runs(baseline: CompletedRun, candidate: CompletedRun) -> RunComparison:
    """Pair identical test cases; all deltas are candidate minus baseline.

    Prompt and provider may differ: they are the experiment's variables.
    Dataset hashes include the selected examples and scorer configuration.
    No database writes or provider calls occur here.
    """
    if baseline.id == candidate.id:
        raise ComparisonError("Choose two distinct evaluation runs")
    for field in ("dataset_name", "dataset_version", "dataset_hash", "dataset_split"):
        if getattr(baseline, field) != getattr(candidate, field):
            raise ComparisonError(
                f"Runs have different {field}; choose the same benchmark and split"
            )
    baseline_results = _validated_results(baseline)
    candidate_results = _validated_results(candidate)
    if baseline_results.keys() != candidate_results.keys():
        raise ComparisonError("Runs have different example IDs; complete the same benchmark first")

    pairs = []
    for example_id in sorted(baseline_results):
        before, after = baseline_results[example_id], candidate_results[example_id]
        if before.input_json != after.input_json:
            raise ComparisonError(f"Example '{example_id}' has conflicting stored inputs")
        delta = after.score - before.score
        pairs.append(
            ExampleComparison(
                example_id=example_id,
                baseline_score=before.score,
                candidate_score=after.score,
                score_delta=delta,
                baseline_passed=before.passed,
                candidate_passed=after.passed,
                change="improved" if delta > 0 else "regressed" if delta < 0 else "unchanged",
            )
        )
    count = len(pairs)
    before_mean = math.fsum(pair.baseline_score for pair in pairs) / count
    after_mean = math.fsum(pair.candidate_score for pair in pairs) / count
    before_pass = sum(pair.baseline_passed for pair in pairs) / count
    after_pass = sum(pair.candidate_passed for pair in pairs) / count
    return RunComparison(
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        dataset_hash=baseline.dataset_hash,
        dataset_split=baseline.dataset_split,
        examples=tuple(pairs),
        baseline_mean_score=before_mean,
        candidate_mean_score=after_mean,
        mean_score_delta=after_mean - before_mean,
        baseline_pass_rate=before_pass,
        candidate_pass_rate=after_pass,
        pass_rate_delta=after_pass - before_pass,
        improved=sum(pair.change == "improved" for pair in pairs),
        regressed=sum(pair.change == "regressed" for pair in pairs),
        unchanged=sum(pair.change == "unchanged" for pair in pairs),
        newly_passing=sum(not pair.baseline_passed and pair.candidate_passed for pair in pairs),
        newly_failing=sum(pair.baseline_passed and not pair.candidate_passed for pair in pairs),
    )
