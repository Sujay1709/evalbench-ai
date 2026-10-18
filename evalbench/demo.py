"""Idempotent seed for the read-only public demo.

The demo replays the standard gate tier and the known-bad automotive prompt
through the offline mock provider. Correlation IDs derive from the dataset,
prompt, and provider content, so reseeding an existing database is a no-op and
an ephemeral host rebuilds identical evidence on every start. Holdout splits
are never seeded, keeping them out of a public site.
"""

import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from evalbench.config import PROJECT_ROOT
from evalbench.datasets import EvaluationSplit, LoadedDataset, load_jsonl
from evalbench.extensions import db
from evalbench.gates import load_gate_config
from evalbench.models import EvaluationRun
from evalbench.prompts import PromptDefinition, load_prompt
from evalbench.providers import Provider
from evalbench.runners import EvaluationRunner

GATE_CONFIG = PROJECT_ROOT / "regression" / "gate.yaml"
DEMO_TIER = "standard"
DEMO_PROVIDER = "mock"
REGRESSION_BENCHMARK = "automotive-development"
REGRESSED_KEY = f"{REGRESSION_BENCHMARK}:known-bad"
KNOWN_BAD_PROMPT = PROJECT_ROOT / "regression" / "fixtures" / "automotive_qa_missing_task.yaml"
_NAMESPACE = uuid.UUID("6f1c2d9e-5b7a-4c3e-9a10-2f4e8d7b6c51")


class DemoSeedError(ValueError):
    """The demo cannot be seeded safely."""


@dataclass(frozen=True)
class DemoRunSpec:
    key: str
    dataset: LoadedDataset
    prompt: PromptDefinition

    @property
    def correlation_id(self) -> uuid.UUID:
        identity = (
            f"{self.key}:{self.dataset.content_hash}:{self.prompt.content_hash}:{DEMO_PROVIDER}"
        )
        return uuid.uuid5(_NAMESPACE, identity)


@dataclass(frozen=True)
class SeededRun:
    key: str
    run: EvaluationRun
    created: bool


def _spec(key: str, dataset_path: Path, prompt_path: Path, split: EvaluationSplit) -> DemoRunSpec:
    return DemoRunSpec(key, load_jsonl(dataset_path).select_split(split), load_prompt(prompt_path))


@lru_cache(maxsize=1)
def demo_run_specs() -> tuple[DemoRunSpec, ...]:
    """Baselines first and the regressed candidate last, so it leads the recent-runs list."""
    config = load_gate_config(GATE_CONFIG)
    specs = []
    for name in config.tier_benchmarks(DEMO_TIER):
        benchmark = config.benchmarks[name]
        specs.append(
            _spec(name, config.resolve(benchmark.dataset), config.resolve(benchmark.prompt),
                  benchmark.split)
        )
    regression = config.benchmarks[REGRESSION_BENCHMARK]
    specs.append(
        _spec(REGRESSED_KEY, config.resolve(regression.dataset), KNOWN_BAD_PROMPT, regression.split)
    )
    return tuple(specs)


def seed_demo(provider: Provider) -> tuple[SeededRun, ...]:
    if provider.name != DEMO_PROVIDER:
        raise DemoSeedError(
            f"The public demo seeds only with the offline '{DEMO_PROVIDER}' provider; "
            f"set LLM_PROVIDER={DEMO_PROVIDER} so no paid model is called."
        )
    runner = EvaluationRunner(provider)
    seeded = []
    for spec in demo_run_specs():
        created = _completed_run(spec.correlation_id) is None
        run = runner.run(spec.dataset, spec.prompt, correlation_id=spec.correlation_id)
        seeded.append(SeededRun(spec.key, run, created))
    return tuple(seeded)


def _completed_run(correlation_id: uuid.UUID) -> EvaluationRun | None:
    return db.session.execute(
        db.select(EvaluationRun).where(
            EvaluationRun.correlation_id == str(correlation_id),
            EvaluationRun.status == "completed",
        )
    ).scalar_one_or_none()


def demo_runs() -> dict[str, EvaluationRun]:
    """Completed demo runs for the current dataset and prompt content, keyed by spec."""
    keys = {str(spec.correlation_id): spec.key for spec in demo_run_specs()}
    runs = db.session.execute(
        db.select(EvaluationRun).where(
            EvaluationRun.correlation_id.in_(keys),
            EvaluationRun.status == "completed",
        )
    ).scalars()
    return {keys[run.correlation_id]: run for run in runs}


def demo_ready() -> bool:
    return len(demo_runs()) == len(demo_run_specs())


def featured_regression() -> tuple[EvaluationRun, EvaluationRun] | None:
    runs = demo_runs()
    baseline, candidate = runs.get(REGRESSION_BENCHMARK), runs.get(REGRESSED_KEY)
    if baseline is None or candidate is None:
        return None
    return baseline, candidate
