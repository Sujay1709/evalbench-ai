from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest
from scipy.stats import bootstrap

from evalbench.comparisons import ComparisonError, compare_runs, paired_bootstrap
from tests.test_comparisons import make_run


def comparison(before=(0.0, 0.5, 1.0), after=(0.25, 0.75, 0.5)):
    return compare_runs(make_run("before", before), make_run("after", after))


def test_intervals_match_scipy_paired_percentile_reference():
    before = np.array([0.0, 0.5, 1.0, 0.25])
    after = np.array([0.25, 0.75, 0.5, 1.0])
    report = paired_bootstrap(comparison(before.tolist(), after.tolist()), n_resamples=1000)
    for statistic, actual in [(np.mean, report.mean_delta), (np.median, report.median_delta)]:
        expected = bootstrap(
            (before, after),
            lambda a, b, axis, statistic=statistic: statistic(b - a, axis=axis),
            paired=True,
            method="percentile",
            n_resamples=1000,
            confidence_level=0.95,
            rng=np.random.Generator(np.random.PCG64(42)),
        )
        assert actual.estimate == pytest.approx(statistic(after - before))
        assert actual.lower == pytest.approx(expected.confidence_interval.low)
        assert actual.upper == pytest.approx(expected.confidence_interval.high)


def test_reproducible_order_independent_and_immutable():
    source = comparison()
    report = paired_bootstrap(source, n_resamples=100)
    assert report == paired_bootstrap(source, n_resamples=100)
    assert report == paired_bootstrap(
        replace(source, examples=tuple(reversed(source.examples))), n_resamples=100
    )
    assert report.sample_size == 3
    assert report.seed == 42
    assert report.method == "paired-percentile"
    assert report.numpy_version == np.__version__
    with pytest.raises(FrozenInstanceError):
        report.mean_delta.lower = 1


def test_identical_pairs_have_zero_interval_despite_varied_scores():
    report = paired_bootstrap(comparison((0, 0.5, 1), (0, 0.5, 1)), n_resamples=100)
    assert report.mean_delta.estimate == report.mean_delta.lower == report.mean_delta.upper == 0
    assert report.median_delta.lower == report.median_delta.upper == 0
    assert any("zero-width" in warning for warning in report.warnings)
    assert any("Small sample" in warning for warning in report.warnings)


def test_constant_improvement_and_reverse_direction():
    forward = paired_bootstrap(comparison((0, 0.25, 0.5), (0.25, 0.5, 0.75)), n_resamples=100)
    backward = paired_bootstrap(comparison((0.25, 0.5, 0.75), (0, 0.25, 0.5)), n_resamples=100)
    assert forward.mean_delta.lower == forward.mean_delta.upper == 0.25
    assert backward.mean_delta.lower == backward.mean_delta.upper == -0.25


@pytest.mark.parametrize(
    "kwargs",
    [{"confidence_level": value} for value in (0, 1, -1, float("nan"), float("inf"), True, "95")]
    + [{"n_resamples": value} for value in (0, 99, 100001, 100.5, True)]
    + [{"seed": value} for value in (-1, 1.5, True, None)],
)
def test_invalid_options_have_actionable_errors(kwargs):
    with pytest.raises(ComparisonError, match=next(iter(kwargs))):
        paired_bootstrap(comparison(), **kwargs)


@pytest.mark.parametrize("size", [0, 1])
def test_insufficient_pairs_rejected(size):
    source = comparison()
    with pytest.raises(ComparisonError, match="at least two"):
        paired_bootstrap(replace(source, examples=source.examples[:size]))


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True, None])
def test_manually_constructed_invalid_scores_rejected(score):
    source = comparison()
    examples = (replace(source.examples[0], candidate_score=score), *source.examples[1:])
    with pytest.raises(ComparisonError, match="finite scores"):
        paired_bootstrap(replace(source, examples=examples))


def test_duplicate_pairs_rejected():
    source = comparison()
    with pytest.raises(ComparisonError, match="unique"):
        paired_bootstrap(replace(source, examples=(source.examples[0], source.examples[0])))


def test_confidence_level_changes_interval_and_records_settings():
    narrow = paired_bootstrap(comparison(), confidence_level=0.5, n_resamples=1000, seed=12)
    wide = paired_bootstrap(comparison(), confidence_level=0.99, n_resamples=1000, seed=12)
    assert wide.mean_delta.lower <= narrow.mean_delta.lower
    assert wide.mean_delta.upper >= narrow.mean_delta.upper
    assert wide.confidence_level == 0.99
    assert wide.n_resamples == 1000
    assert wide.seed == 12
