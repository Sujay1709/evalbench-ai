"""Turn one paired baseline/candidate comparison into explicit gate checks."""

from dataclasses import dataclass
from typing import Literal

from evalbench.comparisons import (
    EfficiencySummary,
    PairedBootstrapResult,
    RunComparison,
    paired_bootstrap,
)
from evalbench.gates.config import GatePolicy

CheckStatus = Literal["passed", "failed", "skipped"]
# Scores are exact fixture values; this only absorbs floating-point summation noise.
_EPSILON = 1e-12


@dataclass(frozen=True)
class GateCheck:
    name: str
    status: CheckStatus
    message: str


@dataclass(frozen=True)
class PolicyEvaluation:
    bootstrap: PairedBootstrapResult | None
    checks: tuple[GateCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.status != "failed" for check in self.checks)


def _newly_failing_check(comparison: RunComparison, policy: GatePolicy) -> GateCheck:
    failing = [
        example.example_id
        for example in comparison.examples
        if example.baseline_passed and not example.candidate_passed
    ]
    allowed = policy.max_newly_failing
    if len(failing) > allowed:
        return GateCheck(
            "newly_failing",
            "failed",
            f"{len(failing)} example(s) passed in the baseline and fail now "
            f"(allowed {allowed}): {', '.join(failing)}",
        )
    return GateCheck(
        "newly_failing", "passed", f"{len(failing)} newly failing example(s) (allowed {allowed})"
    )


def _mean_score_check(
    comparison: RunComparison, bootstrap: PairedBootstrapResult | None, policy: GatePolicy
) -> GateCheck:
    delta = comparison.mean_score_delta
    tolerance = policy.mean_score_tolerance
    if bootstrap is None:
        return GateCheck(
            "mean_score",
            "skipped",
            f"Mean score delta {delta:+.3f}; a paired interval needs at least two examples",
        )
    interval = bootstrap.mean_delta
    summary = (
        f"Mean score delta {delta:+.3f}, {bootstrap.confidence_level:.0%} paired interval "
        f"[{interval.lower:+.3f}, {interval.upper:+.3f}], tolerance {tolerance:.3f}"
    )
    beyond_tolerance = delta + tolerance < -_EPSILON
    if beyond_tolerance and interval.upper < -_EPSILON:
        return GateCheck("mean_score", "failed", f"{summary}: the interval supports a regression")
    if beyond_tolerance:
        return GateCheck(
            "mean_score",
            "passed",
            f"{summary}: the drop exceeds tolerance, but the interval includes no change",
        )
    return GateCheck("mean_score", "passed", summary)


def _latency_check(efficiency: EfficiencySummary, budget: float) -> GateCheck:
    observed = efficiency.p95_generation_ms
    if observed is None:
        return GateCheck(
            "p95_latency", "skipped", "No newly generated responses to measure (all cache hits)"
        )
    status: CheckStatus = "failed" if observed > budget else "passed"
    return GateCheck(
        "p95_latency", status, f"P95 generation latency {observed:.1f} ms (budget {budget:.1f} ms)"
    )


def _cost_check(efficiency: EfficiencySummary, budget: float) -> GateCheck:
    observed = efficiency.estimated_generation_cost_usd
    if observed is None:
        return GateCheck(
            "estimated_cost",
            "failed",
            f"A ${budget:.4f} cost budget is configured, but cost is unknown for "
            f"{efficiency.examples - efficiency.cost_coverage} response(s)",
        )
    status: CheckStatus = "failed" if observed > budget else "passed"
    return GateCheck(
        "estimated_cost",
        status,
        f"Estimated generation cost ${observed:.4f} (budget ${budget:.4f})",
    )


def evaluate_policy(
    comparison: RunComparison, efficiency: EfficiencySummary, policy: GatePolicy
) -> PolicyEvaluation:
    """Fail on newly failing examples, on a mean-score drop beyond tolerance that the
    paired bootstrap interval also supports, or on an exceeded configured budget."""
    bootstrap = None
    if len(comparison.examples) >= 2:
        bootstrap = paired_bootstrap(
            comparison,
            confidence_level=policy.confidence_level,
            n_resamples=policy.bootstrap_resamples,
            seed=policy.bootstrap_seed,
        )
    checks = [
        _newly_failing_check(comparison, policy),
        _mean_score_check(comparison, bootstrap, policy),
    ]
    if policy.max_p95_latency_ms is not None:
        checks.append(_latency_check(efficiency, policy.max_p95_latency_ms))
    if policy.max_estimated_cost_usd is not None:
        checks.append(_cost_check(efficiency, policy.max_estimated_cost_usd))
    return PolicyEvaluation(bootstrap=bootstrap, checks=tuple(checks))
