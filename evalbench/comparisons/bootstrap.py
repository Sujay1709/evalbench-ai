"""Reproducible percentile intervals for paired example score differences."""

import math
from dataclasses import dataclass

import numpy as np

from evalbench.comparisons.paired import ComparisonError, RunComparison


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    lower: float
    upper: float


@dataclass(frozen=True)
class PairedBootstrapResult:
    baseline_run_id: str
    candidate_run_id: str
    sample_size: int
    confidence_level: float
    n_resamples: int
    seed: int
    mean_delta: BootstrapInterval
    median_delta: BootstrapInterval
    warnings: tuple[str, ...]
    method: str = "paired-percentile"
    quantile_method: str = "linear"
    random_generator: str = "PCG64"
    numpy_version: str = np.__version__


def paired_bootstrap(
    comparison: RunComparison,
    *,
    confidence_level: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 42,
) -> PairedBootstrapResult:
    """Estimate intervals for the mean and median of candidate-minus-baseline deltas.

    Resampling deltas is equivalent to resampling paired rows with common indices.
    These intervals describe variation across examples, not repeated model calls.
    """
    if (
        isinstance(confidence_level, bool)
        or not isinstance(confidence_level, (int, float))
        or not math.isfinite(confidence_level)
        or not 0 < confidence_level < 1
    ):
        raise ComparisonError("confidence_level must be finite and strictly between 0 and 1")
    if type(n_resamples) is not int or not 100 <= n_resamples <= 100_000:
        raise ComparisonError("n_resamples must be an integer between 100 and 100000")
    if type(seed) is not int or seed < 0:
        raise ComparisonError("seed must be a nonnegative integer")

    examples = sorted(comparison.examples, key=lambda example: example.example_id)
    if len(examples) < 2:
        raise ComparisonError("Paired bootstrap requires at least two examples")
    if len({example.example_id for example in examples}) != len(examples):
        raise ComparisonError("Paired bootstrap requires unique example IDs")
    for example in examples:
        for score in (example.baseline_score, example.candidate_score):
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ComparisonError("Paired bootstrap requires finite scores in [0, 1]")
    # Derive from the paired scores rather than trusting a manually constructed delta.
    deltas = np.array(
        [example.candidate_score - example.baseline_score for example in examples], dtype=float
    )
    rng = np.random.Generator(np.random.PCG64(seed))
    means = np.empty(n_resamples)
    medians = np.empty(n_resamples)
    # Bound intermediate sample matrices instead of allocating resamples x dataset size.
    batch_size = max(1, min(256, 1_000_000 // len(deltas)))
    for start in range(0, n_resamples, batch_size):
        stop = min(start + batch_size, n_resamples)
        indices = rng.integers(0, len(deltas), size=(stop - start, len(deltas)))
        sampled = deltas[indices]
        means[start:stop] = np.mean(sampled, axis=1)
        medians[start:stop] = np.median(sampled, axis=1)
    tail = (1 - confidence_level) / 2

    def interval(estimate: float, distribution: np.ndarray) -> BootstrapInterval:
        lower, upper = np.quantile(distribution, [tail, 1 - tail], method="linear")
        return BootstrapInterval(float(estimate), float(lower), float(upper))

    warnings = [
        "Assumes independent, representative examples; does not measure model-call variability."
    ]
    if len(deltas) < 30:
        warnings.append("Small sample (fewer than 30 pairs); interval coverage may be unreliable.")
    if np.all(deltas == deltas[0]):
        warnings.append(
            "All observed deltas are identical; a zero-width interval is not certainty."
        )
    return PairedBootstrapResult(
        baseline_run_id=comparison.baseline_run_id,
        candidate_run_id=comparison.candidate_run_id,
        sample_size=len(deltas),
        confidence_level=confidence_level,
        n_resamples=n_resamples,
        seed=seed,
        mean_delta=interval(np.mean(deltas), means),
        median_delta=interval(np.median(deltas), medians),
        warnings=tuple(warnings),
    )
