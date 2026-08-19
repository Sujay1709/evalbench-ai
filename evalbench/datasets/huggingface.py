import json
import random
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from evalbench.datasets.loader import LoadedDataset, load_jsonl
from evalbench.datasets.schemas import EvaluationExample

REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
EvaluationSplit = Literal["development", "holdout"]
LoadDataset = Callable[..., Iterable[Mapping[str, Any]]]


class HuggingFaceImportError(ValueError):
    """A Hugging Face dataset could not be imported reproducibly."""


class HuggingFaceDataset(StrEnum):
    SQUAD_V2 = "squad-v2"
    HOTPOT_QA = "hotpot-qa"


@dataclass(frozen=True)
class HuggingFaceImportSpec:
    dataset: HuggingFaceDataset
    revision: str
    output_path: Path
    source_split: str = "validation"
    target_split: EvaluationSplit = "development"
    sample_size: int = 10
    seed: int = 42
    scan_limit: int = 1_000
    retrieved_at: date = field(default_factory=date.today)
    force: bool = False

    def __post_init__(self) -> None:
        if not REVISION_PATTERN.fullmatch(self.revision):
            raise HuggingFaceImportError(
                "revision must be a full 40-character lowercase Git commit SHA"
            )
        if not self.source_split.strip():
            raise HuggingFaceImportError("source_split cannot be empty")
        if self.target_split not in {"development", "holdout"}:
            raise HuggingFaceImportError(
                "target_split must be either 'development' or 'holdout'"
            )
        if self.sample_size < 1:
            raise HuggingFaceImportError("sample_size must be at least 1")
        if self.scan_limit < self.sample_size:
            raise HuggingFaceImportError("scan_limit must be at least sample_size")
        if self.output_path.suffix.lower() != ".jsonl":
            raise HuggingFaceImportError("output_path must use the .jsonl extension")


@dataclass(frozen=True)
class HuggingFaceImportResult:
    dataset: LoadedDataset
    source_offsets: tuple[int, ...]
    output_path: Path


@dataclass(frozen=True)
class _DatasetProfile:
    dataset_id: str
    config: str
    source_url: str
    license: str
    normalize: Callable[
        [Mapping[str, Any], int, HuggingFaceImportSpec, "_DatasetProfile"],
        EvaluationExample,
    ]


def deterministic_offsets(*, sample_size: int, seed: int, scan_limit: int) -> tuple[int, ...]:
    """Choose stable source positions without downloading the entire dataset."""
    if sample_size < 1:
        raise HuggingFaceImportError("sample_size must be at least 1")
    if scan_limit < sample_size:
        raise HuggingFaceImportError("scan_limit must be at least sample_size")
    return tuple(sorted(random.Random(seed).sample(range(scan_limit), sample_size)))


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HuggingFaceImportError(f"source row requires a non-empty '{key}' value")
    return value.strip()


def _source_id(row: Mapping[str, Any]) -> str:
    for key in ("id", "_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HuggingFaceImportError("source row requires a non-empty 'id' or '_id' value")


def _provenance(
    *,
    source_id: str,
    source_offset: int,
    spec: HuggingFaceImportSpec,
    profile: _DatasetProfile,
) -> dict[str, Any]:
    return {
        "dataset_id": profile.dataset_id,
        "config": profile.config,
        "split": spec.source_split,
        "source_id": source_id,
        "revision": spec.revision,
        "sample_offset": source_offset,
        "source_url": profile.source_url,
        "license": profile.license,
        "retrieved_at": spec.retrieved_at.isoformat(),
    }


def _normalize_squad_v2(
    row: Mapping[str, Any],
    source_offset: int,
    spec: HuggingFaceImportSpec,
    profile: _DatasetProfile,
) -> EvaluationExample:
    source_id = _source_id(row)
    question = _required_text(row, "question")
    context = _required_text(row, "context")
    raw_answers = row.get("answers")
    if not isinstance(raw_answers, Mapping):
        raise HuggingFaceImportError("SQuAD row requires an 'answers' mapping")

    raw_texts = raw_answers.get("text", [])
    if not isinstance(raw_texts, list):
        raise HuggingFaceImportError("SQuAD answers.text must be a list")
    answers = list(
        dict.fromkeys(
            answer.strip()
            for answer in raw_texts
            if isinstance(answer, str) and answer.strip()
        )
    )
    answerable = bool(answers)

    if answerable:
        mock_response = answers[0]
        scorers = [
            {
                "type": "token_f1",
                "accepted_answers": answers,
                "threshold": 1.0,
            },
            {"type": "answerability", "expected_answerable": True},
        ]
        response_format = "Return only the shortest supported answer."
        tags = ["squad-v2", "grounded-qa", "answerable"]
    else:
        mock_response = "insufficient evidence"
        scorers = [
            {
                "type": "answerability",
                "expected_answerable": False,
                "abstention_phrases": ["insufficient evidence"],
            }
        ]
        response_format = (
            "Return only the shortest supported answer, or the required abstention phrase."
        )
        tags = ["squad-v2", "grounded-qa", "unanswerable", "abstention"]

    return EvaluationExample.model_validate(
        {
            "id": f"squad-v2-{source_id}",
            "input": {
                "context": context,
                "question": question,
                "response_format": response_format,
            },
            "mock_response": mock_response,
            "scorers": scorers,
            "tags": tags,
            "difficulty": "medium",
            "split": spec.target_split,
            "provenance": _provenance(
                source_id=source_id,
                source_offset=source_offset,
                spec=spec,
                profile=profile,
            ),
        }
    )


def _hotpot_context(row: Mapping[str, Any]) -> str:
    raw_context = row.get("context")
    if not isinstance(raw_context, Mapping):
        raise HuggingFaceImportError("HotpotQA row requires a 'context' mapping")

    titles = raw_context.get("title")
    sentence_groups = raw_context.get("sentences")
    if not isinstance(titles, list) or not isinstance(sentence_groups, list):
        raise HuggingFaceImportError("HotpotQA context requires title and sentences lists")
    if len(titles) != len(sentence_groups):
        raise HuggingFaceImportError("HotpotQA context titles and sentences are misaligned")

    paragraphs: list[str] = []
    for title, sentences in zip(titles, sentence_groups, strict=True):
        if not isinstance(title, str) or not isinstance(sentences, list):
            raise HuggingFaceImportError("HotpotQA context contains an invalid paragraph")
        paragraph = " ".join(
            sentence.strip()
            for sentence in sentences
            if isinstance(sentence, str) and sentence.strip()
        )
        if paragraph:
            paragraphs.append(f"[{title.strip()}] {paragraph}")

    if not paragraphs:
        raise HuggingFaceImportError("HotpotQA context contains no usable text")
    return "\n".join(paragraphs)


def _normalize_hotpot_qa(
    row: Mapping[str, Any],
    source_offset: int,
    spec: HuggingFaceImportSpec,
    profile: _DatasetProfile,
) -> EvaluationExample:
    source_id = _source_id(row)
    question = _required_text(row, "question")
    answer = _required_text(row, "answer")
    question_type = str(row.get("type", "unknown")).strip().lower()
    level = str(row.get("level", "hard")).strip().lower()
    difficulty = level if level in {"easy", "medium", "hard"} else "hard"
    tags = ["hotpot-qa", "multi-hop", "distractor"]
    if question_type in {"bridge", "comparison"}:
        tags.append(question_type)

    return EvaluationExample.model_validate(
        {
            "id": f"hotpot-{source_id}",
            "input": {
                "context": _hotpot_context(row),
                "question": question,
                "response_format": "Return only the shortest supported answer.",
            },
            "mock_response": answer,
            "scorers": [
                {
                    "type": "token_f1",
                    "accepted_answers": [answer],
                    "threshold": 1.0,
                },
                {"type": "answerability", "expected_answerable": True},
            ],
            "tags": tags,
            "difficulty": difficulty,
            "split": spec.target_split,
            "provenance": _provenance(
                source_id=source_id,
                source_offset=source_offset,
                spec=spec,
                profile=profile,
            ),
        }
    )


DATASET_PROFILES = {
    HuggingFaceDataset.SQUAD_V2: _DatasetProfile(
        dataset_id="rajpurkar/squad_v2",
        config="squad_v2",
        source_url="https://huggingface.co/datasets/rajpurkar/squad_v2",
        license="CC-BY-SA-4.0",
        normalize=_normalize_squad_v2,
    ),
    HuggingFaceDataset.HOTPOT_QA: _DatasetProfile(
        dataset_id="hotpotqa/hotpot_qa",
        config="distractor",
        source_url="https://huggingface.co/datasets/hotpotqa/hotpot_qa",
        license="CC-BY-SA-4.0",
        normalize=_normalize_hotpot_qa,
    ),
}


def _default_load_dataset(**kwargs: Any) -> Iterable[Mapping[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise HuggingFaceImportError(
            "Hugging Face import requires the 'datasets' dependency; "
            "install requirements.txt first"
        ) from exc
    return load_dataset(**kwargs)


def _selected_rows(
    stream: Iterable[Mapping[str, Any]], offsets: tuple[int, ...]
) -> list[tuple[int, Mapping[str, Any]]]:
    wanted = set(offsets)
    selected: list[tuple[int, Mapping[str, Any]]] = []
    last_offset = -1

    for source_offset, row in enumerate(stream):
        last_offset = source_offset
        if source_offset in wanted:
            selected.append((source_offset, row))
        if source_offset >= offsets[-1]:
            break

    if len(selected) != len(offsets):
        raise HuggingFaceImportError(
            "source split ended before all deterministic offsets were available "
            f"(highest observed offset: {last_offset}, requested: {offsets[-1]})"
        )
    return selected


def _write_jsonl(
    examples: list[EvaluationExample], output_path: Path, *, force: bool
) -> LoadedDataset:
    output_path = output_path.resolve()
    if output_path.exists() and not force:
        raise HuggingFaceImportError(
            f"output already exists: {output_path}; pass --force to replace it"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for example in examples:
                payload = example.model_dump(by_alias=True, exclude_none=True, mode="json")
                stream.write(
                    json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True,
                    )
                )
                stream.write("\n")

        # Validate the serialized artifact before making it the final file.
        load_jsonl(temporary_path)
        temporary_path.replace(output_path)
        return load_jsonl(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def import_huggingface_dataset(
    spec: HuggingFaceImportSpec,
    *,
    load_dataset_fn: LoadDataset | None = None,
) -> HuggingFaceImportResult:
    resolved_output = spec.output_path.resolve()
    if resolved_output.exists() and not spec.force:
        raise HuggingFaceImportError(
            f"output already exists: {resolved_output}; pass --force to replace it"
        )

    profile = DATASET_PROFILES[spec.dataset]
    offsets = deterministic_offsets(
        sample_size=spec.sample_size,
        seed=spec.seed,
        scan_limit=spec.scan_limit,
    )
    loader = load_dataset_fn or _default_load_dataset

    try:
        stream = loader(
            path=profile.dataset_id,
            name=profile.config,
            split=spec.source_split,
            revision=spec.revision,
            streaming=True,
        )
        rows = _selected_rows(stream, offsets)
        examples = [
            profile.normalize(row, source_offset, spec, profile)
            for source_offset, row in rows
        ]
    except HuggingFaceImportError:
        raise
    except Exception as exc:
        raise HuggingFaceImportError(
            f"failed to stream {profile.dataset_id}@{spec.revision}: {exc}"
        ) from exc

    dataset = _write_jsonl(examples, spec.output_path, force=spec.force)
    return HuggingFaceImportResult(
        dataset=dataset,
        source_offsets=offsets,
        output_path=spec.output_path.resolve(),
    )
