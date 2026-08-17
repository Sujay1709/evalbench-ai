from evalbench.datasets import load_jsonl
from tests.conftest import PROJECT_ROOT


def test_dataset_hash_is_stable():
    dataset_path = PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"

    first = load_jsonl(dataset_path)
    second = load_jsonl(dataset_path)

    assert len(first.examples) == 5
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64
