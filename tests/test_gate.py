"""Offline unit checks for the regression gate's policy, config, baselines, and reports."""

import json
import math
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from evalbench.comparisons import EfficiencySummary, compare_runs
from evalbench.datasets import EvaluationExample, EvaluationSplit, load_jsonl
from evalbench.gates import (
    BaselineError,
    BaselineSnapshot,
    GateConfigError,
    GatePolicy,
    evaluate_policy,
    github_annotations,
    json_report,
    junit_report,
    load_baseline,
    load_gate_config,
    step_summary,
)
from evalbench.gates.baseline import baseline_run, check_baseline_identity
from evalbench.gates.runner import BenchmarkOutcome, GateReport, PromptIdentity
from evalbench.providers import MockProvider
from evalbench.providers.mock import MOCK_ABSTENTION
from tests.conftest import PROJECT_ROOT

GATE_CONFIG = PROJECT_ROOT / "regression" / "gate.yaml"
POLICY = GatePolicy(
    max_newly_failing=0,
    mean_score_tolerance=0.02,
    confidence_level=0.95,
    bootstrap_resamples=1_000,
    bootstrap_seed=7,
)


def make_run(run_id, outcomes):
    """outcomes: (score, passed) per example, so score and pass state vary independently."""
    return SimpleNamespace(
        id=run_id,
        status="completed",
        dataset_name="test",
        dataset_version="v1",
        dataset_hash="a" * 64,
        dataset_split="development",
        total_examples=len(outcomes),
        passed_examples=sum(passed for _, passed in outcomes),
        mean_score=math.fsum(score for score, _ in outcomes) / len(outcomes),
        results=[
            SimpleNamespace(
                example_id=f"ex-{index:02d}",
                score=score,
                passed=passed,
                input_json={"question": str(index)},
            )
            for index, (score, passed) in enumerate(outcomes)
        ],
    )


def make_efficiency(*, p95=1.0, cost=0.0, examples=10, coverage=10):
    return EfficiencySummary(
        examples=examples,
        cache_hits=0,
        generated=examples,
        median_generation_ms=p95,
        p95_generation_ms=p95,
        input_tokens=0,
        output_tokens=0,
        estimated_generation_cost_usd=cost,
        estimated_new_response_cost_usd=cost,
        cost_coverage=coverage,
        cost_bases=(),
    )


def evaluate(baseline, candidate, policy=POLICY, efficiency=None):
    comparison = compare_runs(make_run("baseline", baseline), make_run("candidate", candidate))
    return comparison, evaluate_policy(comparison, efficiency or make_efficiency(), policy)


def statuses(evaluation):
    return {check.name: check.status for check in evaluation.checks}


def message(evaluation, name):
    return next(check.message for check in evaluation.checks if check.name == name)


def test_mock_abstains_only_when_the_prompt_hides_the_question_or_context():
    example = EvaluationExample(
        id="mock-1",
        input={
            "question": "What is the warranty?",
            "context": "The warranty is 8 years.",
            "reference": "8 years",
        },
        mock_response="8 years",
        scorers=[{"type": "exact_match", "expected": "8 years"}],
    )
    provider = MockProvider()

    shown = provider.generate("Context: The warranty is 8 years. Q: What is the warranty?", example)
    no_question = provider.generate("Context: The warranty is 8 years.", example)

    assert shown.text == "8 years"
    assert "hidden_inputs" not in shown.metadata
    assert no_question.text == MOCK_ABSTENTION
    assert no_question.metadata["hidden_inputs"] == ["question"]


def test_unchanged_candidate_passes_every_check():
    outcomes = [(1.0, True)] * 10
    _, evaluation = evaluate(outcomes, outcomes)

    assert evaluation.passed
    assert statuses(evaluation) == {"newly_failing": "passed", "mean_score": "passed"}


def test_a_newly_failing_example_fails_even_when_the_mean_barely_moves():
    baseline = [(1.0, True)] * 10
    candidate = [(1.0, True)] * 9 + [(0.9, False)]
    _, evaluation = evaluate(baseline, candidate)

    assert not evaluation.passed
    assert statuses(evaluation) == {"newly_failing": "failed", "mean_score": "passed"}
    assert "ex-09" in message(evaluation, "newly_failing")


def test_a_mean_drop_fails_only_when_the_paired_interval_supports_it():
    _, consistent = evaluate([(1.0, True)] * 10, [(0.5, True)] * 10)
    _, noisy = evaluate([(1.0, True)] * 3, [(0.0, True), (1.0, True), (1.0, True)])

    assert statuses(consistent)["mean_score"] == "failed"
    assert "supports a regression" in message(consistent, "mean_score")
    assert statuses(noisy)["mean_score"] == "passed"
    assert "includes no change" in message(noisy, "mean_score")


def test_a_drop_within_the_practical_tolerance_passes():
    _, evaluation = evaluate([(1.0, True)] * 10, [(1.0, True)] * 9 + [(0.9, True)])

    assert evaluation.passed
    assert "-0.010" in message(evaluation, "mean_score")


def test_a_single_example_skips_the_interval_but_keeps_the_hard_check():
    _, evaluation = evaluate([(1.0, True)], [(0.0, False)])

    assert evaluation.bootstrap is None
    assert statuses(evaluation) == {"newly_failing": "failed", "mean_score": "skipped"}


def test_optional_budgets_fail_closed_when_cost_is_unknown():
    outcomes = [(1.0, True)] * 10
    policy = POLICY.model_copy(update={"max_p95_latency_ms": 100.0, "max_estimated_cost_usd": 1.0})

    _, slow = evaluate(outcomes, outcomes, policy, make_efficiency(p95=250.0))
    _, cached = evaluate(outcomes, outcomes, policy, make_efficiency(p95=None))
    _, unknown_cost = evaluate(outcomes, outcomes, policy, make_efficiency(cost=None, coverage=4))
    _, unbudgeted = evaluate(outcomes, outcomes)

    assert statuses(slow)["p95_latency"] == "failed"
    assert statuses(cached)["p95_latency"] == "skipped"
    assert statuses(unknown_cost)["estimated_cost"] == "failed"
    assert "unknown for 6 response(s)" in message(unknown_cost, "estimated_cost")
    assert {"p95_latency", "estimated_cost"}.isdisjoint(statuses(unbudgeted))


def test_committed_config_resolves_every_benchmark_and_keeps_holdout_out_of_ci_tiers():
    config = load_gate_config(GATE_CONFIG)

    assert set(config.tiers) == {"smoke", "standard", "full"}
    assert set(config.tier_benchmarks("full")) == set(config.benchmarks)
    for spec in config.benchmarks.values():
        assert config.resolve(spec.dataset).is_file()
        assert config.resolve(spec.prompt).is_file()
    for tier in ("smoke", "standard"):
        splits = {config.benchmarks[name].split for name in config.tier_benchmarks(tier)}
        assert splits == {EvaluationSplit.DEVELOPMENT}
    with pytest.raises(GateConfigError, match="Unknown tier"):
        config.tier_benchmarks("nightly")


def test_committed_baselines_match_their_configured_datasets():
    config = load_gate_config(GATE_CONFIG)

    for name in config.tier_benchmarks("full"):
        spec = config.benchmarks[name]
        dataset = load_jsonl(config.resolve(spec.dataset)).select_split(spec.split)
        snapshot = load_baseline(config.baseline_path("mock", name))
        check_baseline_identity(snapshot, benchmark=name, provider="mock", dataset=dataset)
        assert snapshot.to_json() == config.baseline_path("mock", name).read_text()


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"tiers": {"smoke": ["missing"]}}, "unknown benchmarks"),
        ({"tiers": {"smoke": ["one", "one"]}}, "more than once"),
        ({"tiers": {"smoke": []}}, "at least one benchmark"),
        ({"benchmarks": {"Bad Name": {}}}, "String should match pattern"),
        ({"policy": {"mean_score_tolerance": 2}}, "less than or equal to 1"),
        ({"surprise": True}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_gate_configs_are_rejected(tmp_path, change, error):
    raw = {
        "version": 1,
        "policy": POLICY.model_dump(mode="json"),
        "benchmarks": {"one": {"dataset": "d.jsonl", "prompt": "p.yaml", "split": "development"}},
        "tiers": {"smoke": ["one"]},
    }
    for key, value in change.items():
        raw[key] = {**raw[key], **value} if key == "policy" else value
    path = tmp_path / "gate.yaml"
    path.write_text(json.dumps(raw))

    with pytest.raises(GateConfigError, match=error):
        load_gate_config(path)


def test_baselines_reject_duplicates_bad_scores_and_stale_identities():
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )
    fields = {
        "benchmark": "automotive-development",
        "provider": "mock",
        "dataset_name": dataset.name,
        "dataset_version": dataset.version,
        "dataset_hash": dataset.content_hash,
        "dataset_split": "development",
        "prompt_id": "automotive-qa",
        "prompt_version": "v1",
        "prompt_hash": "b" * 64,
    }
    examples = [
        {"example_id": example.id, "score": 1.0, "passed": True} for example in dataset.examples
    ]
    snapshot = BaselineSnapshot(**fields, examples=examples)

    with pytest.raises(ValueError, match="unique"):
        BaselineSnapshot(**fields, examples=examples + examples[:1])
    with pytest.raises(ValueError, match="less than or equal to 1"):
        BaselineSnapshot(**fields, examples=[{**examples[0], "score": 1.5}])
    with pytest.raises(BaselineError, match="provider 'mock'"):
        check_baseline_identity(
            snapshot, benchmark="automotive-development", provider="openai", dataset=dataset
        )
    stale = snapshot.model_copy(update={"dataset_hash": "0" * 64})
    with pytest.raises(BaselineError, match="stale"):
        check_baseline_identity(
            stale, benchmark="automotive-development", provider="mock", dataset=dataset
        )
    as_run = baseline_run(snapshot, dataset)
    assert (as_run.total_examples, as_run.passed_examples, as_run.mean_score) == (3, 3, 1.0)


def _report():
    baseline_outcomes = [(1.0, True)] * 10
    comparison, evaluation = evaluate(baseline_outcomes, [(0.5, False)] + [(1.0, True)] * 9)
    snapshot = BaselineSnapshot(
        benchmark="alpha",
        provider="mock",
        dataset_name="test",
        dataset_version="v1",
        dataset_hash="a" * 64,
        dataset_split="development",
        prompt_id="p",
        prompt_version="v1",
        prompt_hash="b" * 64,
        examples=[
            {"example_id": f"ex-{index:02d}", "score": 1.0, "passed": True} for index in range(10)
        ],
    )
    failing = BenchmarkOutcome(
        benchmark="alpha",
        dataset_path="datasets/alpha.jsonl",
        split="development",
        candidate_prompt_path="prompts/p.yaml",
        baseline=snapshot,
        candidate_prompt=PromptIdentity("prompts/p.yaml", "p", "v2", "c" * 64),
        candidate_run_id="run-alpha",
        comparison=comparison,
        efficiency=make_efficiency(),
        evaluation=evaluation,
    )
    broken = BenchmarkOutcome(
        benchmark="beta",
        dataset_path="datasets/beta.jsonl",
        split="development",
        candidate_prompt_path="prompts/p.yaml",
        error="Baseline for 'beta' is stale:\n100% different",
    )
    return GateReport("standard", "mock", "regression/gate.yaml", POLICY, (failing, broken))


def test_errors_take_precedence_over_regressions_in_the_exit_code():
    report = _report()

    assert [outcome.status for outcome in report.outcomes] == ["failed", "error"]
    assert (report.status, report.exit_code) == ("error", 2)


def test_json_report_records_policy_prompt_change_and_example_deltas():
    data = json.loads(json_report(_report()))

    assert data["config"]["policy_hash"] == POLICY.content_hash
    alpha, beta = data["benchmarks"]
    assert alpha["prompt_changed"] is True
    assert alpha["summary"]["newly_failing"] == 1
    assert alpha["examples"][0] == {
        "example_id": "ex-00",
        "baseline_score": 1.0,
        "candidate_score": 0.5,
        "score_delta": -0.5,
        "baseline_passed": True,
        "candidate_passed": False,
        "change": "regressed",
    }
    assert beta["status"] == "error"
    assert "stale" in beta["error"]


def test_junit_report_counts_check_example_and_error_testcases():
    root = ElementTree.fromstring(junit_report(_report()))

    assert root.get("tests") == "13"
    assert root.get("failures") == "2"
    assert root.get("errors") == "1"
    alpha = root.find("testsuite[@name='alpha']")
    failed_cases = [case.get("name") for case in alpha if case.find("failure") is not None]
    assert failed_cases == ["newly_failing", "ex-00"]


def test_annotations_are_single_line_and_escaped():
    lines = github_annotations(_report())

    assert len(lines) == 2
    assert all("\n" not in line for line in lines)
    assert lines[0].startswith("::error title=EvalBench gate%3A alpha::1 example(s)")
    assert lines[1].endswith("stale:%0A100%25 different")


def test_step_summary_lists_each_benchmark_and_problem():
    summary = step_summary(_report())

    assert "## EvalBench regression gate: ERROR" in summary
    assert "| alpha | failed | -0.050 | 1 |" in summary
    assert "| beta | error | n/a | n/a |" in summary
    assert "**alpha:** 1 example(s) passed in the baseline" in summary
