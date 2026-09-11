"""Read-only presentation helpers for comparison pages."""

from evalbench.comparisons import compare_segments
from evalbench.config import PROJECT_ROOT
from evalbench.datasets import EvaluationSplit, load_jsonl


def load_segments(baseline, candidate):
    root = (PROJECT_ROOT / "datasets").resolve()
    if any(
        not value or "/" in value or "\\" in value or value in {".", ".."}
        for value in (baseline.dataset_name, baseline.dataset_version)
    ):
        raise ValueError("Invalid dataset identity")
    path = (root / baseline.dataset_name / f"{baseline.dataset_version}.jsonl").resolve()
    if not path.is_relative_to(root):
        raise ValueError("Dataset path is outside the registry")
    dataset = load_jsonl(path).select_split(EvaluationSplit(baseline.dataset_split))
    return compare_segments(baseline, candidate, dataset)
