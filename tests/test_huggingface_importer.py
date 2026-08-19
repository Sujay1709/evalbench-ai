from datetime import date

import pytest

from evalbench.datasets import (
    HuggingFaceDataset,
    HuggingFaceImportError,
    HuggingFaceImportSpec,
    deterministic_offsets,
    import_huggingface_dataset,
    load_jsonl,
)

REVISION = "a" * 40


def _squad_row(index: int, *, answerable: bool = True) -> dict:
    return {
        "id": f"squad-{index}",
        "question": f"Question {index}?",
        "context": f"Context {index} contains the answer.",
        "answers": {
            "text": [f"answer {index}"] if answerable else [],
            "answer_start": [0] if answerable else [],
        },
    }


def _hotpot_row(index: int) -> dict:
    return {
        "id": f"hotpot-{index}",
        "question": f"Which answer belongs to row {index}?",
        "answer": f"answer {index}",
        "type": "bridge",
        "level": "hard",
        "context": {
            "title": ["First article", "Second article"],
            "sentences": [
                ["The first supporting sentence."],
                ["The second supporting sentence."],
            ],
        },
    }


def test_deterministic_offsets_are_reproducible_and_unique():
    first = deterministic_offsets(sample_size=4, seed=17, scan_limit=20)
    second = deterministic_offsets(sample_size=4, seed=17, scan_limit=20)

    assert first == second
    assert first == tuple(sorted(first))
    assert len(set(first)) == 4


@pytest.mark.parametrize(
    "sample_size,scan_limit",
    [(0, 10), (3, 2)],
)
def test_deterministic_offsets_reject_invalid_windows(sample_size, scan_limit):
    with pytest.raises(HuggingFaceImportError):
        deterministic_offsets(
            sample_size=sample_size,
            seed=42,
            scan_limit=scan_limit,
        )


def test_squad_import_is_pinned_normalized_and_round_trippable(tmp_path):
    captured: dict = {}

    def fake_loader(**kwargs):
        captured.update(kwargs)
        return iter(
            [
                _squad_row(0),
                _squad_row(1, answerable=False),
                _squad_row(2),
                _squad_row(3),
            ]
        )

    output_path = tmp_path / "squad" / "generated.jsonl"
    spec = HuggingFaceImportSpec(
        dataset=HuggingFaceDataset.SQUAD_V2,
        revision=REVISION,
        output_path=output_path,
        target_split="holdout",
        sample_size=2,
        seed=6,
        scan_limit=4,
        retrieved_at=date(2026, 8, 18),
    )

    result = import_huggingface_dataset(spec, load_dataset_fn=fake_loader)
    reloaded = load_jsonl(output_path)

    assert captured == {
        "path": "rajpurkar/squad_v2",
        "name": "squad_v2",
        "split": "validation",
        "revision": REVISION,
        "streaming": True,
    }
    assert len(reloaded.examples) == 2
    assert reloaded.content_hash == result.dataset.content_hash
    assert {example.split for example in reloaded.examples} == {"holdout"}
    assert {"answerable", "unanswerable"} <= {
        tag for example in reloaded.examples for tag in example.tags
    }
    assert {example.mock_response for example in reloaded.examples} == {
        "answer 0",
        "insufficient evidence",
    }
    assert all(example.provenance is not None for example in reloaded.examples)
    assert {
        example.provenance.sample_offset for example in reloaded.examples if example.provenance
    } == set(result.source_offsets)
    assert all(example.provenance.revision == REVISION for example in reloaded.examples)


def test_hotpot_import_preserves_distractor_context_and_metadata(tmp_path):
    def fake_loader(**kwargs):
        del kwargs
        return iter([_hotpot_row(0)])

    spec = HuggingFaceImportSpec(
        dataset=HuggingFaceDataset.HOTPOT_QA,
        revision=REVISION,
        output_path=tmp_path / "hotpot.jsonl",
        sample_size=1,
        scan_limit=1,
    )

    result = import_huggingface_dataset(spec, load_dataset_fn=fake_loader)
    example = result.dataset.examples[0]

    assert "[First article]" in example.input["context"]
    assert "[Second article]" in example.input["context"]
    assert {"hotpot-qa", "multi-hop", "distractor", "bridge"} <= set(example.tags)
    assert example.difficulty == "hard"
    assert example.provenance is not None
    assert example.provenance.dataset_id == "hotpotqa/hotpot_qa"
    assert example.provenance.config == "distractor"


def test_import_refuses_to_replace_existing_output_without_force(tmp_path):
    output_path = tmp_path / "existing.jsonl"
    output_path.write_text("existing content")
    spec = HuggingFaceImportSpec(
        dataset=HuggingFaceDataset.SQUAD_V2,
        revision=REVISION,
        output_path=output_path,
        sample_size=1,
        scan_limit=1,
    )

    loader_called = False

    def fake_loader(**kwargs):
        nonlocal loader_called
        del kwargs
        loader_called = True
        return iter([_squad_row(0)])

    with pytest.raises(HuggingFaceImportError, match="output already exists"):
        import_huggingface_dataset(
            spec,
            load_dataset_fn=fake_loader,
        )

    assert not loader_called
    assert output_path.read_text() == "existing content"


def test_import_reports_when_stream_is_shorter_than_sampling_window(tmp_path):
    spec = HuggingFaceImportSpec(
        dataset=HuggingFaceDataset.SQUAD_V2,
        revision=REVISION,
        output_path=tmp_path / "short.jsonl",
        sample_size=2,
        seed=1,
        scan_limit=100,
    )

    with pytest.raises(HuggingFaceImportError, match="source split ended"):
        import_huggingface_dataset(
            spec,
            load_dataset_fn=lambda **kwargs: iter([_squad_row(0)]),
        )
