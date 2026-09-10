"""Descriptive subgroup comparisons using verified dataset metadata."""

import math
from dataclasses import dataclass
from typing import Literal

from evalbench.comparisons.paired import (
    ComparisonError,
    CompletedRun,
    ExampleComparison,
    compare_runs,
)
from evalbench.datasets.loader import LoadedDataset, _content_hash


@dataclass(frozen=True)
class SegmentSummary:
    dimension: Literal["tag", "difficulty"]
    label: str | None
    example_ids: tuple[str, ...]
    sample_size: int
    baseline_mean_score: float
    candidate_mean_score: float
    mean_score_delta: float
    baseline_pass_rate: float
    candidate_pass_rate: float
    pass_rate_delta: float
    improved: int
    regressed: int
    unchanged: int
    newly_passing: int
    newly_failing: int


@dataclass(frozen=True)
class SegmentComparison:
    baseline_run_id: str
    candidate_run_id: str
    dataset_hash: str
    dataset_split: str
    tags: tuple[SegmentSummary, ...]
    difficulties: tuple[SegmentSummary, ...]


def _summarize(
    dimension: Literal["tag", "difficulty"],
    label: str | None,
    pairs: list[ExampleComparison],
) -> SegmentSummary:
    count = len(pairs)
    before = math.fsum(pair.baseline_score for pair in pairs) / count
    after = math.fsum(pair.candidate_score for pair in pairs) / count
    before_pass = sum(pair.baseline_passed for pair in pairs) / count
    after_pass = sum(pair.candidate_passed for pair in pairs) / count
    return SegmentSummary(
        dimension=dimension,
        label=label,
        example_ids=tuple(pair.example_id for pair in pairs),
        sample_size=count,
        baseline_mean_score=before,
        candidate_mean_score=after,
        mean_score_delta=after - before,
        baseline_pass_rate=before_pass,
        candidate_pass_rate=after_pass,
        pass_rate_delta=after_pass - before_pass,
        improved=sum(pair.change == "improved" for pair in pairs),
        regressed=sum(pair.change == "regressed" for pair in pairs),
        unchanged=sum(pair.change == "unchanged" for pair in pairs),
        newly_passing=sum(not pair.baseline_passed and pair.candidate_passed for pair in pairs),
        newly_failing=sum(pair.baseline_passed and not pair.candidate_passed for pair in pairs),
    )


def compare_segments(
    baseline: CompletedRun, candidate: CompletedRun, dataset: LoadedDataset
) -> SegmentComparison:
    """Group paired results; tags overlap, while difficulty groups partition rows.

    Dataset metadata is not stored on result rows. Require its original content
    identity rather than relabeling historical runs with a newer dataset file.
    """
    comparison = compare_runs(baseline, candidate)
    if (
        dataset.name != baseline.dataset_name
        or dataset.version != baseline.dataset_version
        or dataset.selected_split != comparison.dataset_split
        or dataset.content_hash != comparison.dataset_hash
        or _content_hash(dataset.examples) != dataset.content_hash
    ):
        raise ComparisonError("Load the original dataset version and select the run's split")
    metadata = {example.id: example for example in dataset.examples}
    if (
        len(metadata) != len(dataset.examples)
        or set(metadata) != {pair.example_id for pair in comparison.examples}
        or any(example.split != dataset.selected_split for example in dataset.examples)
    ):
        raise ComparisonError("Dataset must contain exactly the run's selected example IDs")

    tags: dict[str | None, list[ExampleComparison]] = {}
    difficulties: dict[str, list[ExampleComparison]] = {}
    for pair in comparison.examples:
        example = metadata[pair.example_id]
        if any(not isinstance(tag, str) or not tag.strip() for tag in example.tags):
            raise ComparisonError(f"Example '{example.id}' requires nonblank string tags")
        if example.difficulty not in {"easy", "medium", "hard"}:
            raise ComparisonError(f"Example '{example.id}' has an invalid difficulty")
        # None represents untagged rows without colliding with a literal tag name.
        for tag in set(example.tags) or {None}:
            tags.setdefault(tag, []).append(pair)
        difficulties.setdefault(example.difficulty, []).append(pair)
    return SegmentComparison(
        baseline_run_id=comparison.baseline_run_id,
        candidate_run_id=comparison.candidate_run_id,
        dataset_hash=comparison.dataset_hash,
        dataset_split=comparison.dataset_split,
        tags=tuple(
            _summarize("tag", label, tags[label])
            for label in sorted(tags, key=lambda label: (label is not None, label or ""))
        ),
        difficulties=tuple(
            _summarize("difficulty", label, difficulties[label])
            for label in ("easy", "medium", "hard")
            if label in difficulties
        ),
    )
