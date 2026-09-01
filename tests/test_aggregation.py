import math

import pytest

from evalbench.runners.aggregation import AggregationError, aggregate_example_scores


def test_aggregate_example_scores_calculates_pass_count_and_mean():
    metrics = aggregate_example_scores([(True, 1.0), (False, 0.25), (True, 0.75)])

    assert metrics.passed_examples == 2
    assert metrics.mean_score == pytest.approx(2 / 3)
    assert metrics.total_examples == 3


def test_aggregate_example_scores_rejects_an_empty_run():
    with pytest.raises(AggregationError, match="without example results"):
        aggregate_example_scores([])


@pytest.mark.parametrize("invalid_score", [-0.1, 1.1, math.inf])
def test_aggregate_example_scores_rejects_invalid_values(invalid_score):
    with pytest.raises(AggregationError, match="finite and between 0 and 1"):
        aggregate_example_scores([(True, invalid_score)])
