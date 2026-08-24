import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from evalbench.datasets.schemas import EvaluationExample, EvaluationSplit


class DatasetValidationError(ValueError):
    pass


class DatasetSplitError(DatasetValidationError):
    """A dataset cannot satisfy the requested evaluation-split policy."""


@dataclass(frozen=True)
class LoadedDataset:
    name: str
    version: str
    examples: tuple[EvaluationExample, ...]
    content_hash: str
    selected_split: EvaluationSplit | None = None

    def select_split(self, split: EvaluationSplit) -> "LoadedDataset":
        selected_examples = tuple(example for example in self.examples if example.split == split)
        if not selected_examples:
            raise DatasetSplitError(
                f"Dataset '{self.name}:{self.version}' contains no '{split.value}' examples"
            )

        return LoadedDataset(
            name=self.name,
            version=self.version,
            examples=selected_examples,
            content_hash=_content_hash(selected_examples),
            selected_split=split,
        )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _content_hash(examples: tuple[EvaluationExample, ...] | list[EvaluationExample]) -> str:
    canonical_examples = [
        example.model_dump(by_alias=True, exclude_none=True, mode="json") for example in examples
    ]
    return hashlib.sha256(_canonical_json(canonical_examples).encode()).hexdigest()


def load_jsonl(path: str | Path) -> LoadedDataset:
    dataset_path = Path(path)
    examples: list[EvaluationExample] = []
    seen_ids: set[str] = set()

    if not dataset_path.is_file():
        raise DatasetValidationError(f"Dataset not found: {dataset_path}")

    for line_number, raw_line in enumerate(dataset_path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            example = EvaluationExample.model_validate_json(raw_line)
        except (ValidationError, ValueError) as exc:
            raise DatasetValidationError(
                f"Invalid dataset row at line {line_number}: {exc}"
            ) from exc

        if example.id in seen_ids:
            raise DatasetValidationError(f"Duplicate example id '{example.id}'")
        seen_ids.add(example.id)
        examples.append(example)

    if not examples:
        raise DatasetValidationError("Dataset contains no examples")

    return LoadedDataset(
        name=dataset_path.parent.name,
        version=dataset_path.stem,
        examples=tuple(examples),
        content_hash=_content_hash(examples),
    )
