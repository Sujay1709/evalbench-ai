import pytest
from pydantic import ValidationError

from evalbench.datasets import DatasetProvenance, load_jsonl
from tests.conftest import PROJECT_ROOT


def test_dataset_hash_is_stable():
    dataset_path = PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"

    first = load_jsonl(dataset_path)
    second = load_jsonl(dataset_path)

    assert len(first.examples) == 5
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


@pytest.mark.parametrize(
    ("relative_path", "dataset_id", "revision", "expected_tags"),
    [
        (
            "datasets/squad_v2/sample_v1.jsonl",
            "rajpurkar/squad_v2",
            "3ffb306f725f7d2ce8394bc1873b24868140c412",
            {"answerable", "unanswerable"},
        ),
        (
            "datasets/hotpot_qa/sample_v1.jsonl",
            "hotpotqa/hotpot_qa",
            "1908d6afbbead072334abe2965f91bd2709910ab",
            {"bridge", "comparison"},
        ),
    ],
)
def test_external_samples_include_pinned_provenance(
    relative_path, dataset_id, revision, expected_tags
):
    dataset = load_jsonl(PROJECT_ROOT / relative_path)

    assert len(dataset.examples) == 4
    assert {example.split for example in dataset.examples} == {
        "development",
        "holdout",
    }
    source_ids = set()
    for example in dataset.examples:
        provenance = example.provenance
        assert provenance is not None
        assert provenance.dataset_id == dataset_id
        assert provenance.revision == revision
        source_ids.add(provenance.source_id)

    assert len(source_ids) == 4
    assert expected_tags <= {tag for example in dataset.examples for tag in example.tags}


@pytest.mark.parametrize("source_url", ["https://", "http://example.com/dataset"])
def test_dataset_provenance_requires_a_complete_https_url(source_url):
    with pytest.raises(ValidationError):
        DatasetProvenance(
            dataset_id="example/dataset",
            config="default",
            split="validation",
            source_id="row-1",
            revision="a" * 40,
            sample_offset=0,
            source_url=source_url,
            license="CC-BY-SA-4.0",
            retrieved_at="2026-08-17",
        )
