from copy import deepcopy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from evalbench.comparisons import ComparisonError, compare_runs
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider, ProviderResponse
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


def make_run(run_id, scores=(1.0, 0.0, 0.5)):
    return SimpleNamespace(
        id=run_id,
        status="completed",
        dataset_name="test",
        dataset_version="v1",
        dataset_hash="a" * 64,
        dataset_split="development",
        total_examples=len(scores),
        passed_examples=sum(score >= 0.5 for score in scores),
        mean_score=sum(scores) / len(scores) if scores else 0,
        results=[
            SimpleNamespace(
                example_id=f"example-{index}",
                score=score,
                passed=score >= 0.5,
                input_json={"question": str(index)},
            )
            for index, score in enumerate(scores)
        ],
    )


def test_comparison_pairs_by_id_and_preserves_sources():
    baseline = make_run("baseline")
    candidate = make_run("candidate", (0.0, 1.0, 0.5))
    candidate.results.reverse()
    original = deepcopy((baseline, candidate))
    comparison = compare_runs(baseline, candidate)
    assert [pair.score_delta for pair in comparison.examples] == [-1, 1, 0]
    assert (comparison.improved, comparison.regressed, comparison.unchanged) == (1, 1, 1)
    assert (comparison.newly_passing, comparison.newly_failing) == (1, 1)
    assert comparison.mean_score_delta == 0
    assert comparison.pass_rate_delta == 0
    assert (baseline, candidate) == original
    with pytest.raises(FrozenInstanceError):
        comparison.examples[0].score_delta = 99


def test_score_changes_and_pass_transitions_are_independent():
    comparison = compare_runs(make_run("before", (0.1,)), make_run("after", (0.4,)))
    assert comparison.improved == 1
    assert comparison.newly_passing == 0
    assert comparison.mean_score_delta == pytest.approx(0.3)
    assert comparison.pass_rate_delta == 0


@pytest.mark.parametrize(
    "field", ["dataset_name", "dataset_version", "dataset_hash", "dataset_split"]
)
def test_rejects_incompatible_benchmarks(field):
    candidate = make_run("candidate")
    setattr(candidate, field, "different")
    with pytest.raises(ComparisonError, match=field):
        compare_runs(make_run("baseline"), candidate)


@pytest.mark.parametrize("status", ["queued", "running", "failed"])
def test_rejects_unfinished_runs(status):
    candidate = make_run("candidate")
    candidate.status = status
    with pytest.raises(ComparisonError, match="must be completed"):
        compare_runs(make_run("baseline"), candidate)


def test_rejects_same_run_and_legacy_split():
    baseline = make_run("baseline")
    with pytest.raises(ComparisonError, match="distinct"):
        compare_runs(baseline, baseline)
    candidate = make_run("candidate")
    baseline.dataset_split = candidate.dataset_split = "legacy_mixed"
    with pytest.raises(ComparisonError, match="development or holdout"):
        compare_runs(baseline, candidate)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, True, "invalid", None])
def test_rejects_invalid_scores(score):
    candidate = make_run("candidate")
    candidate.results[0].score = score
    with pytest.raises(ComparisonError, match="finite score"):
        compare_runs(make_run("baseline"), candidate)


@pytest.mark.parametrize(
    "defect, message",
    [
        ("missing", "coverage"),
        ("duplicate", "duplicate"),
        ("extra", "coverage"),
        ("different_id", "different example IDs"),
        ("input", "conflicting stored inputs"),
        ("mean", "aggregate metrics"),
        ("passes", "aggregate metrics"),
        ("passed_type", "boolean"),
    ],
)
def test_rejects_corrupted_evidence(defect, message):
    candidate = make_run("candidate")
    if defect == "missing":
        candidate.results.pop()
    elif defect == "duplicate":
        candidate.results[1].example_id = candidate.results[0].example_id
    elif defect == "extra":
        candidate.results.append(
            SimpleNamespace(
                example_id="extra",
                score=1.0,
                passed=True,
                input_json={},
            )
        )
    elif defect == "different_id":
        candidate.results[0].example_id = "replacement"
    elif defect == "input":
        candidate.results[0].input_json = {"question": "tampered"}
    elif defect == "mean":
        candidate.mean_score = 0
    elif defect == "passes":
        candidate.passed_examples = 0
    elif defect == "passed_type":
        candidate.results[0].passed = 1
    with pytest.raises(ComparisonError, match=message):
        compare_runs(make_run("baseline"), candidate)


def test_rejects_empty_runs():
    with pytest.raises(ComparisonError, match="coverage"):
        compare_runs(make_run("before", ()), make_run("after", ()))


def test_persisted_regression_is_identified_without_calls_or_writes(app):
    class DegradedProvider(MockProvider):
        name = "degraded-mock"

        def generate(self, prompt, example):
            if example.id == "auto-001":
                return ProviderResponse(text="incorrect", latency_ms=0)
            return super().generate(prompt, example)

    dataset = load_jsonl(PROJECT_ROOT / "datasets/automotive_qa/v1.jsonl").select_split(
        EvaluationSplit.DEVELOPMENT
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts/automotive_qa/v1.yaml")
    with app.app_context():
        baseline = EvaluationRunner(MockProvider()).run(dataset, prompt)
        candidate = EvaluationRunner(DegradedProvider()).run(dataset, prompt)
        comparison = compare_runs(baseline, candidate)
        assert comparison.mean_score_delta == pytest.approx(-1 / 3)
        assert comparison.pass_rate_delta == pytest.approx(-1 / 3)
        assert comparison.newly_failing == 1
        assert [pair.example_id for pair in comparison.examples if pair.change == "regressed"] == [
            "auto-001",
        ]
        assert not db.session.new and not db.session.dirty and not db.session.deleted
        assert db.session.query(EvaluationRun).count() == 2
        assert db.session.query(ExampleResult).count() == 6
