"""Configurable, non-mutating readiness checks for a calibrated judge."""

from __future__ import annotations

import math
from dataclasses import dataclass

from evalbench.judges.calibration import CalibrationReport


@dataclass(frozen=True)
class CalibrationReadinessPolicy:
    """Operator-selected minimum evidence and agreement for a holdout cohort."""

    minimum_results: int = 10
    minimum_exact_agreement: float = 0.8
    minimum_kappa_lower_bound: float = 0.4

    def __post_init__(self) -> None:
        if type(self.minimum_results) is not int or self.minimum_results < 2:
            raise ValueError("minimum_results must be an integer of at least 2")
        if (
            type(self.minimum_exact_agreement) not in (int, float)
            or not math.isfinite(self.minimum_exact_agreement)
            or not 0 <= self.minimum_exact_agreement <= 1
        ):
            raise ValueError("minimum_exact_agreement must be between 0 and 1")
        if (
            type(self.minimum_kappa_lower_bound) not in (int, float)
            or not math.isfinite(self.minimum_kappa_lower_bound)
            or not -1 <= self.minimum_kappa_lower_bound <= 1
        ):
            raise ValueError("minimum_kappa_lower_bound must be between -1 and 1")


@dataclass(frozen=True)
class CalibrationReadiness:
    """Outcome and reasons; this never changes a run or makes a release."""

    eligible: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]


def assess_calibration_readiness(
    report: CalibrationReport,
    *,
    dataset_split: str,
    policy: CalibrationReadinessPolicy,
) -> CalibrationReadiness:
    """Check evidence against explicit thresholds, requiring a holdout cohort."""
    failures: list[str] = []
    checks = (
        f"{report.overall.result_count} labeled results (minimum {policy.minimum_results})",
        f"exact agreement {report.overall.exact_agreement:.3f} "
        f"(minimum {policy.minimum_exact_agreement:.3f})",
    )
    if dataset_split != "holdout":
        failures.append("Calibration readiness requires an explicitly selected holdout cohort")
    if report.overall.result_count < policy.minimum_results:
        failures.append("The selected cohort is smaller than the configured minimum")
    if report.overall.exact_agreement < policy.minimum_exact_agreement:
        failures.append("Exact agreement is below the configured minimum")

    interval = report.overall.kappa_interval
    if interval is None:
        failures.append("A weighted-kappa confidence interval could not be estimated")
        checks += ("weighted-kappa lower confidence bound unavailable",)
    else:
        checks += (
            f"weighted-kappa lower {interval.confidence_level:.0%} bound "
            f"{interval.low:.3f} (minimum {policy.minimum_kappa_lower_bound:.3f})",
        )
        if interval.low < policy.minimum_kappa_lower_bound:
            failures.append("The weighted-kappa lower confidence bound is below the minimum")

    return CalibrationReadiness(
        eligible=not failures,
        checks=checks,
        failures=tuple(failures),
    )
