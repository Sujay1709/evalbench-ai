from dataclasses import dataclass
from pathlib import Path

from evalbench.config import PROJECT_ROOT
from evalbench.datasets import EvaluationSplit, LoadedDataset, load_jsonl
from evalbench.models import EvaluationRun
from evalbench.prompts import PromptDefinition, load_prompt


@dataclass(frozen=True)
class EvaluationArtifacts:
    dataset: LoadedDataset
    prompt: PromptDefinition


def _registry_path(root: Path, category: str, artifact_id: str, version: str, suffix: str) -> Path:
    """Resolve identifiers inside a registry without allowing path traversal."""

    if Path(artifact_id).name != artifact_id or Path(version).name != version:
        raise ValueError(f"Invalid {category} identifier or version")

    registry_root = (root / category).resolve()
    path = (registry_root / artifact_id / f"{version}{suffix}").resolve()
    if not path.is_relative_to(registry_root):
        raise ValueError(f"Invalid {category} registry path")
    return path


def _load_registered_prompt(root: Path, prompt_id: str, version: str) -> PromptDefinition:
    if Path(prompt_id).name != prompt_id or Path(version).name != version:
        raise ValueError("Invalid prompt identifier or version")

    prompt_root = (root / "prompts").resolve()
    matches: list[PromptDefinition] = []
    for candidate in prompt_root.glob(f"*/{version}.yaml"):
        prompt = load_prompt(candidate)
        if prompt.id == prompt_id and prompt.version == version:
            matches.append(prompt)

    if not matches:
        raise ValueError(f"Prompt '{prompt_id}:{version}' is not registered")
    if len(matches) > 1:
        raise ValueError(f"Prompt '{prompt_id}:{version}' is registered more than once")
    return matches[0]


def load_run_artifacts(
    run: EvaluationRun,
    *,
    project_root: Path = PROJECT_ROOT,
) -> EvaluationArtifacts:
    """Reconstruct and verify immutable inputs referenced by a persisted run."""

    try:
        split = EvaluationSplit(run.dataset_split)
    except ValueError as exc:
        raise ValueError(
            f"Evaluation run '{run.id}' has unsupported dataset split '{run.dataset_split}'"
        ) from exc

    dataset_path = _registry_path(
        project_root,
        "datasets",
        run.dataset_name,
        run.dataset_version,
        ".jsonl",
    )
    dataset = load_jsonl(dataset_path).select_split(split)
    if dataset.content_hash != run.dataset_hash:
        raise ValueError(
            f"Dataset content hash does not match evaluation run '{run.id}'"
        )
    if len(dataset.examples) != run.total_examples:
        raise ValueError(
            f"Dataset example count does not match evaluation run '{run.id}'"
        )

    prompt = _load_registered_prompt(project_root, run.prompt_id, run.prompt_version)

    return EvaluationArtifacts(dataset=dataset, prompt=prompt)
