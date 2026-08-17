import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from evalbench.datasets.schemas import EvaluationExample


class DatasetValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedDataset:
    name: str
    version: str
    examples: tuple[EvaluationExample, ...]
    content_hash: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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

    canonical_examples = [
        example.model_dump(by_alias=True, exclude_none=True, mode="json") for example in examples
    ]
    content_hash = hashlib.sha256(_canonical_json(canonical_examples).encode()).hexdigest()

    return LoadedDataset(
        name=dataset_path.parent.name,
        version=dataset_path.stem,
        examples=tuple(examples),
        content_hash=content_hash,
    )
