from copy import deepcopy
from types import SimpleNamespace

import pytest

from evalbench.comparisons.efficiency import build_leaderboards, summarize_efficiency
from evalbench.config import Settings
from evalbench.providers.usage import usage_snapshot
from tests.test_comparisons import make_run


def run_with_usage(run_id="run", cost=0.25, scores=(1.0, 0.0, 0.5)):
    run = make_run(run_id, scores)
    run.provider = "test"
    run.prompt_id = "test"
    run.prompt_version = "v1"
    for index, result in enumerate(run.results):
        result.latency_ms = [10, 20, 100][index]
        result.cache_hit = False
        result.usage_json = {
            "input_tokens": 10,
            "output_tokens": 2,
            "estimated_cost_usd": cost,
            "cost_basis": "fixture estimate",
        }
    return run


def test_efficiency_uses_generated_latencies_and_preserves_sources():
    run = run_with_usage()
    run.results[-1].cache_hit = True
    run.results[-1].latency_ms = 0
    original = deepcopy(run)
    report = summarize_efficiency(run)
    assert report.median_generation_ms == 15
    assert report.p95_generation_ms == 19.5
    assert report.input_tokens == 30
    assert report.output_tokens == 6
    assert report.estimated_generation_cost_usd == 0.75
    assert report.estimated_new_response_cost_usd == 0.5
    assert report.cache_hits == 1
    assert run == original


def test_unknown_cost_is_not_zero_or_partial_sum():
    run = run_with_usage()
    run.results[0].usage_json = None
    report = summarize_efficiency(run)
    assert report.estimated_generation_cost_usd is None
    assert report.estimated_new_response_cost_usd is None
    assert report.input_tokens is None
    assert report.cost_coverage == 2


def test_cache_only_is_not_zero_generation_latency():
    run = run_with_usage()
    for result in run.results:
        result.cache_hit = True
    report = summarize_efficiency(run)
    assert report.median_generation_ms is None
    assert report.p95_generation_ms is None
    assert report.estimated_new_response_cost_usd == 0
    assert report.estimated_generation_cost_usd == 0.75


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "1"])
def test_invalid_measurements_are_unknown(value):
    usage = usage_snapshot({"input_tokens": value, "estimated_cost_usd": value})
    assert usage["input_tokens"] is None
    assert usage["estimated_cost_usd"] is None
    run = run_with_usage()
    run.results[0].latency_ms = value
    assert summarize_efficiency(run).p95_generation_ms is None


def test_pareto_dominance_ties_unknown_and_benchmark_isolation():
    best = run_with_usage("best", 0.1, (1, 1, 1))
    tied = run_with_usage("tied", 0.1, (1, 1, 1))
    worse = run_with_usage("worse", 0.2)
    unknown = run_with_usage("unknown", None)
    separate = run_with_usage("separate", 0)
    separate.dataset_split = "holdout"
    failed = run_with_usage("failed")
    failed.status = "failed"
    boards, excluded = build_leaderboards([worse, best, unknown, tied, separate, failed])
    assert len(boards) == 2
    assert excluded == ("failed",)
    entries = {entry.run_id: entry for board in boards for entry in board.entries}
    assert entries["best"].pareto is True
    assert entries["tied"].pareto is True
    assert entries["worse"].pareto is False
    assert entries["unknown"].pareto is None
    assert entries["separate"].pareto is True


def test_conflicting_inputs_are_excluded_from_leaderboard():
    first = run_with_usage("a")
    second = run_with_usage("b")
    second.results[0].input_json = {"changed": True}
    boards, excluded = build_leaderboards([first, second])
    assert excluded == ("b",)
    assert len(boards[0].entries) == 1


def test_empty_summary_and_board():
    assert summarize_efficiency(SimpleNamespace(results=[])).estimated_generation_cost_usd is None
    assert build_leaderboards([]) == ((), ())


def test_price_configuration_requires_both_prices():
    with pytest.raises(ValueError, match="both OpenAI"):
        Settings(_env_file=None, openai_input_usd_per_million=1)
