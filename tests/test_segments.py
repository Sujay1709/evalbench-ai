from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from evalbench.comparisons import ComparisonError, compare_segments
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.datasets.loader import LoadedDataset, _content_hash
from evalbench.datasets.schemas import EvaluationExample
from evalbench.extensions import db
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT
from tests.test_comparisons import make_run


def fixtures():
    baseline = make_run("before", (1, 0, 0.5))
    candidate = make_run("after", (0, 1, 0.5))
    examples = tuple(
        EvaluationExample(
            id=result.example_id,
            input=result.input_json,
            mock_response="test",
            scorers=[{"type": "exact_match", "expected": "test"}],
            tags=tags,
            difficulty=difficulty,
        )
        for result, tags, difficulty in zip(
            baseline.results,
            (["safety", "shared", "safety"], ["shared"], []),
            ("hard", "easy", "medium"),
            strict=True,
        )
    )
    dataset = LoadedDataset(
        "test", "v1", examples, _content_hash(examples), EvaluationSplit.DEVELOPMENT
    )
    baseline.dataset_hash = candidate.dataset_hash = dataset.content_hash
    return baseline, candidate, dataset


def test_overlapping_tags_hidden_regression_and_untagged_rows():
    baseline, candidate, dataset = fixtures()
    original = deepcopy((baseline, candidate, dataset))
    report = compare_segments(baseline, candidate, dataset)
    tags = {segment.label: segment for segment in report.tags}
    assert list(tags) == [None, "safety", "shared"]
    assert tags["safety"].sample_size == 1  # Duplicate tags never double-count a row.
    assert tags["safety"].mean_score_delta == -1
    assert tags["safety"].pass_rate_delta == -1
    assert tags["safety"].newly_failing == tags["safety"].regressed == 1
    assert tags["shared"].mean_score_delta == 0
    assert tags["shared"].newly_passing == tags["shared"].improved == 1
    assert tags[None].example_ids == ("example-2",)
    assert tags[None].unchanged == 1
    assert [segment.label for segment in report.difficulties] == ["easy", "medium", "hard"]
    assert sum(segment.sample_size for segment in report.difficulties) == 3
    assert sum(segment.sample_size for segment in report.tags) == 4
    assert (baseline, candidate, dataset) == original
    with pytest.raises(FrozenInstanceError):
        report.tags[0].sample_size = 5
    candidate.results.reverse()
    assert compare_segments(baseline, candidate, dataset) == report


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "wrong"),
        ("version", "v2"),
        ("content_hash", "wrong"),
        ("selected_split", None),
        ("selected_split", EvaluationSplit.HOLDOUT),
    ],
)
def test_rejects_wrong_dataset_identity(field, value):
    baseline, candidate, dataset = fixtures()
    with pytest.raises(ComparisonError, match="original dataset"):
        compare_segments(baseline, candidate, replace(dataset, **{field: value}))


def test_rejects_metadata_mutated_after_hashing():
    baseline, candidate, dataset = fixtures()
    dataset.examples[0].tags.append("edited")
    with pytest.raises(ComparisonError, match="original dataset"):
        compare_segments(baseline, candidate, dataset)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "split", "blank_tag"])
def test_rejects_invalid_metadata_even_with_matching_hash(defect):
    baseline, candidate, dataset = fixtures()
    if defect == "missing":
        dataset = replace(dataset, examples=dataset.examples[:-1])
    elif defect == "duplicate":
        dataset = replace(dataset, examples=dataset.examples + (dataset.examples[0],))
    elif defect == "split":
        dataset.examples[0].split = EvaluationSplit.HOLDOUT
    else:
        dataset.examples[0].tags = [" "]
    dataset = replace(dataset, content_hash=_content_hash(dataset.examples))
    baseline.dataset_hash = candidate.dataset_hash = dataset.content_hash
    with pytest.raises(ComparisonError, match="example IDs|nonblank"):
        compare_segments(baseline, candidate, dataset)


def test_run_compatibility_checks_are_preserved():
    baseline, candidate, dataset = fixtures()
    candidate.status = "failed"
    with pytest.raises(ComparisonError, match="completed"):
        compare_segments(baseline, candidate, dataset)


@pytest.mark.parametrize(
    "dataset_path,count",
    [
        ("automotive_qa/v1.jsonl", 3),
        ("squad_v2/sample_v1.jsonl", 2),
        ("hotpot_qa/sample_v1.jsonl", 2),
    ],
)
def test_real_persisted_dataset_breakdowns_are_read_only(app, dataset_path, count):
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / dataset_path).select_split(
        EvaluationSplit.DEVELOPMENT
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts/automotive_qa/v1.yaml")
    with app.app_context():
        baseline = EvaluationRunner(MockProvider()).run(dataset, prompt)
        candidate = EvaluationRunner(MockProvider()).run(dataset, prompt)
        report = compare_segments(baseline, candidate, dataset)
        assert sum(segment.sample_size for segment in report.difficulties) == count
        assert all(segment.mean_score_delta == 0 for segment in report.tags)
        assert not db.session.new and not db.session.dirty and not db.session.deleted
