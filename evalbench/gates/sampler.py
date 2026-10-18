"""Audit a confidence-budgeted sample against the full paired suite.

The schedule is fixed: hard examples, then tag, then example id. Sampling may
stop once every tag and difficulty in the suite has its minimum coverage and the
paired mean-delta interval is beyond the minimum detectable effect. Saved calls
are reported only when that early decision matches the decision on every
example. This module is not used by ``evalbench gate``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from evalbench.comparisons.bootstrap import paired_bootstrap
from evalbench.comparisons.paired import ExampleComparison, RunComparison

_DIFFICULTY_ORDER = {"hard": 0, "medium": 1, "easy": 2}


class AdaptiveSampleError(ValueError):
    """The simulated suite cannot support an adaptive-sampling audit."""


@dataclass(frozen=True)
class SampledExample:
    """One paired outcome the sampler may purchase, with its slice labels."""

    example_id: str
    tag: str
    difficulty: str
    baseline_score: float
    candidate_score: float
    estimated_cost_usd: float


@dataclass(frozen=True)
class SamplerPolicy:
    """Thresholds for the simulation. They are not estimated from a model."""

    minimum_per_slice: int = 2
    minimum_detectable_effect: float = 0.05
    confidence_level: float = 0.95
    n_resamples: int = 100
    seed: int = 42


@dataclass(frozen=True)
class IntervalSnapshot:
    sample_size: int
    estimate: float
    lower: float
    upper: float


@dataclass(frozen=True)
class AdaptiveSampleAudit:
    sampling_order: tuple[str, ...]
    sampled_ids: tuple[str, ...]
    stop_reason: str
    interval_history: tuple[IntervalSnapshot, ...]
    model_call_count: int
    estimated_cost_usd: float
    adaptive_decision: str
    full_suite_decision: str
    decisions_agree: bool
    saved_calls: int | None


def audit_adaptive_sample(
    examples: Sequence[SampledExample], policy: SamplerPolicy | None = None
) -> AdaptiveSampleAudit:
    """Walk the fixed schedule and compare an early stop with the full suite."""

    chosen = policy or SamplerPolicy()
    _validate_policy(chosen)
    ordered = _ordered(_validate_examples(examples))
    required_tags, required_difficulties = _required_coverage(ordered, chosen.minimum_per_slice)
    history: list[IntervalSnapshot] = []
    sampled: list[SampledExample] = []
    seen_tags: dict[str, int] = {}
    seen_difficulties: dict[str, int] = {}
    stop_reason = "full_suite"
    adaptive_decision = "inconclusive"

    for example in ordered:
        sampled.append(example)
        seen_tags[example.tag] = seen_tags.get(example.tag, 0) + 1
        seen_difficulties[example.difficulty] = seen_difficulties.get(example.difficulty, 0) + 1
        if len(sampled) < 2:
            continue
        snapshot, decision = _interval_decision(sampled, chosen)
        history.append(snapshot)
        covered = _covered(seen_tags, required_tags) and _covered(
            seen_difficulties, required_difficulties
        )
        if covered and decision != "inconclusive":
            stop_reason = "conclusive_interval"
            adaptive_decision = decision
            break
        adaptive_decision = decision

    full_decision = _interval_decision(ordered, chosen)[1] if len(ordered) >= 2 else "inconclusive"
    agree = adaptive_decision == full_decision
    unsampled = len(ordered) - len(sampled)
    saved = unsampled if agree and stop_reason == "conclusive_interval" else (0 if agree else None)
    return AdaptiveSampleAudit(
        sampling_order=tuple(example.example_id for example in ordered),
        sampled_ids=tuple(example.example_id for example in sampled),
        stop_reason=stop_reason,
        interval_history=tuple(history),
        model_call_count=len(sampled),
        estimated_cost_usd=sum(example.estimated_cost_usd for example in sampled),
        adaptive_decision=adaptive_decision,
        full_suite_decision=full_decision,
        decisions_agree=agree,
        saved_calls=saved,
    )


def _validate_policy(policy: SamplerPolicy) -> None:
    if type(policy.minimum_per_slice) is not int or policy.minimum_per_slice < 1:
        raise AdaptiveSampleError("minimum_per_slice must be an integer of at least 1")
    effect = policy.minimum_detectable_effect
    if isinstance(effect, bool) or not isinstance(effect, (int, float)) or not 0 < effect <= 1:
        raise AdaptiveSampleError("minimum_detectable_effect must be greater than 0 and at most 1")
    if type(policy.n_resamples) is not int or policy.n_resamples < 100:
        raise AdaptiveSampleError("n_resamples must be an integer of at least 100")
    if type(policy.seed) is not int or policy.seed < 0:
        raise AdaptiveSampleError("seed must be a nonnegative integer")


def _validate_examples(examples: Sequence[SampledExample]) -> tuple[SampledExample, ...]:
    if len(examples) < 2:
        raise AdaptiveSampleError("Adaptive sampling needs at least two paired examples")
    seen: set[str] = set()
    for example in examples:
        if not example.example_id or example.example_id in seen:
            raise AdaptiveSampleError("Example ids must be non-empty and unique")
        seen.add(example.example_id)
        if not example.tag.strip():
            raise AdaptiveSampleError(f"Example '{example.example_id}' needs a tag")
        if example.difficulty not in _DIFFICULTY_ORDER:
            raise AdaptiveSampleError(
                f"Example '{example.example_id}' difficulty must be easy, medium, or hard"
            )
        for score in (example.baseline_score, example.candidate_score):
            numeric = not isinstance(score, bool) and isinstance(score, (int, float))
            if not numeric or not 0 <= score <= 1:
                raise AdaptiveSampleError(
                    f"Example '{example.example_id}' scores must be finite and between 0 and 1"
                )
        cost = example.estimated_cost_usd
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise AdaptiveSampleError(
                f"Example '{example.example_id}' cost must be a nonnegative number"
            )
    return tuple(examples)


def _ordered(examples: Sequence[SampledExample]) -> tuple[SampledExample, ...]:
    return tuple(
        sorted(
            examples,
            key=lambda example: (
                _DIFFICULTY_ORDER[example.difficulty],
                example.tag,
                example.example_id,
            ),
        )
    )


def _required_coverage(
    examples: Sequence[SampledExample], minimum: int
) -> tuple[dict[str, int], dict[str, int]]:
    tags: dict[str, int] = {}
    difficulties: dict[str, int] = {}
    for example in examples:
        tags[example.tag] = tags.get(example.tag, 0) + 1
        difficulties[example.difficulty] = difficulties.get(example.difficulty, 0) + 1
    return (
        {name: min(count, minimum) for name, count in tags.items()},
        {name: min(count, minimum) for name, count in difficulties.items()},
    )


def _covered(seen: dict[str, int], required: dict[str, int]) -> bool:
    return all(seen.get(name, 0) >= count for name, count in required.items())


def _interval_decision(
    examples: Sequence[SampledExample], policy: SamplerPolicy
) -> tuple[IntervalSnapshot, str]:
    result = paired_bootstrap(
        _comparison(examples),
        confidence_level=policy.confidence_level,
        n_resamples=policy.n_resamples,
        seed=policy.seed,
    )
    estimate = result.mean_delta
    snapshot = IntervalSnapshot(
        sample_size=result.sample_size,
        estimate=estimate.estimate,
        lower=estimate.lower,
        upper=estimate.upper,
    )
    effect = policy.minimum_detectable_effect
    if estimate.upper < 0 and estimate.estimate <= -effect:
        decision = "regression"
    elif estimate.lower > 0 and estimate.estimate >= effect:
        decision = "no_regression"
    else:
        decision = "inconclusive"
    return snapshot, decision


def _comparison(examples: Sequence[SampledExample]) -> RunComparison:
    rows = []
    for example in examples:
        delta = example.candidate_score - example.baseline_score
        if delta > 0:
            change = "improved"
        elif delta < 0:
            change = "regressed"
        else:
            change = "unchanged"
        rows.append(
            ExampleComparison(
                example_id=example.example_id,
                baseline_score=example.baseline_score,
                candidate_score=example.candidate_score,
                score_delta=delta,
                baseline_passed=example.baseline_score == 1,
                candidate_passed=example.candidate_score == 1,
                change=change,
            )
        )
    baseline_mean = sum(example.baseline_score for example in examples) / len(examples)
    candidate_mean = sum(example.candidate_score for example in examples) / len(examples)
    baseline_pass = sum(row.baseline_passed for row in rows) / len(rows)
    candidate_pass = sum(row.candidate_passed for row in rows) / len(rows)
    return RunComparison(
        baseline_run_id="simulation-baseline",
        candidate_run_id="simulation-candidate",
        dataset_hash="simulation",
        dataset_split="development",
        examples=tuple(rows),
        baseline_mean_score=baseline_mean,
        candidate_mean_score=candidate_mean,
        mean_score_delta=candidate_mean - baseline_mean,
        baseline_pass_rate=baseline_pass,
        candidate_pass_rate=candidate_pass,
        pass_rate_delta=candidate_pass - baseline_pass,
        improved=sum(row.change == "improved" for row in rows),
        regressed=sum(row.change == "regressed" for row in rows),
        unchanged=sum(row.change == "unchanged" for row in rows),
        newly_passing=sum(
            (not row.baseline_passed) and row.candidate_passed for row in rows
        ),
        newly_failing=sum(row.baseline_passed and not row.candidate_passed for row in rows),
    )
