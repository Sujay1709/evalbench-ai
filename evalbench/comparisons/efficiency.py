"""Read-only efficiency summaries and compatible benchmark leaderboards."""

import math
from dataclasses import dataclass

import numpy as np

from evalbench.comparisons.paired import ComparisonError, _validated_results, compare_runs
from evalbench.providers.usage import usage_snapshot


@dataclass(frozen=True)
class EfficiencySummary:
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


def summarize_efficiency(run) -> EfficiencySummary:
    results = list(run.results)
    generated = [result for result in results if not result.cache_hit]
    latencies = [result.latency_ms for result in generated]
    valid_latency = bool(latencies) and all(
        type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in latencies
    )
    usages = [usage_snapshot(result.usage_json or {}) for result in results]

    def total(key, indices):
        values = [usages[index][key] for index in indices]
        if not results or any(value is None for value in values):
            return None
        return sum(values)

    return EfficiencySummary(
        examples=len(results),
        cache_hits=len(results) - len(generated),
        generated=len(generated),
        median_generation_ms=float(np.median(latencies)) if valid_latency else None,
        p95_generation_ms=float(np.quantile(latencies, 0.95, method="linear"))
        if valid_latency
        else None,
        input_tokens=total("input_tokens", range(len(results))),
        output_tokens=total("output_tokens", range(len(results))),
        estimated_generation_cost_usd=total("estimated_cost_usd", range(len(results))),
        estimated_new_response_cost_usd=total(
            "estimated_cost_usd", [i for i, result in enumerate(results) if not result.cache_hit]
        ),
        cost_coverage=sum(usage["estimated_cost_usd"] is not None for usage in usages),
        cost_bases=tuple(sorted({usage["cost_basis"] for usage in usages if usage["cost_basis"]})),
    )


@dataclass(frozen=True)
class LeaderboardEntry:
    run_id: str
    provider: str
    prompt: str
    mean_score: float
    efficiency: EfficiencySummary
    pareto: bool | None


@dataclass(frozen=True)
class BenchmarkBoard:
    identity: tuple[str, str, str, str]
    entries: tuple[LeaderboardEntry, ...]


def build_leaderboards(runs) -> tuple[tuple[BenchmarkBoard, ...], tuple[str, ...]]:
    groups = {}
    excluded = []
    for run in sorted(runs, key=lambda run: run.id):
        identity = (run.dataset_name, run.dataset_version, run.dataset_hash, run.dataset_split)
        try:
            _validated_results(run)
            if identity in groups:
                compare_runs(groups[identity][0], run)
        except ComparisonError:
            excluded.append(run.id)
            continue
        groups.setdefault(identity, []).append(run)
    boards = []
    for identity, group in sorted(groups.items()):
        summaries = {run.id: summarize_efficiency(run) for run in group}
        entries = []
        for run in sorted(group, key=lambda run: (-run.mean_score, run.id)):
            efficiency = summaries[run.id]
            cost = efficiency.estimated_generation_cost_usd
            dominated = cost is not None and any(
                other.id != run.id
                and (other_cost := summaries[other.id].estimated_generation_cost_usd) is not None
                and other_cost <= cost
                and other.mean_score >= run.mean_score
                and (other_cost < cost or other.mean_score > run.mean_score)
                for other in group
            )
            entries.append(
                LeaderboardEntry(
                    run.id,
                    run.provider,
                    f"{run.prompt_id} {run.prompt_version}",
                    run.mean_score,
                    efficiency,
                    None if cost is None else not dominated,
                )
            )
        boards.append(BenchmarkBoard(identity, tuple(entries)))
    return tuple(boards), tuple(excluded)
