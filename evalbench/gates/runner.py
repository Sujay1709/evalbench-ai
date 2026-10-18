"""Run a gate tier against committed baselines; callers provide the app context."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evalbench.comparisons import (
    EfficiencySummary,
    RunComparison,
    compare_runs,
    summarize_efficiency,
)
from evalbench.datasets import load_jsonl
from evalbench.gates.baseline import (
    BaselineSnapshot,
    baseline_run,
    check_baseline_identity,
    load_baseline,
    snapshot_from_run,
)
from evalbench.gates.config import GateConfig, GateConfigError, GatePolicy
from evalbench.gates.policy import PolicyEvaluation, evaluate_policy
from evalbench.judges.passport import JudgePassport, release_gate_block
from evalbench.prompts import load_prompt
from evalbench.providers import Provider, ProviderError
from evalbench.runners import EvaluationRunner

OutcomeStatus = Literal["passed", "failed", "error"]


@dataclass(frozen=True)
class PromptIdentity:
    path: str
    id: str
    version: str
    content_hash: str


@dataclass(frozen=True)
class BenchmarkOutcome:
    benchmark: str
    dataset_path: str
    split: str
    candidate_prompt_path: str
    error: str | None = None
    baseline: BaselineSnapshot | None = None
    candidate_prompt: PromptIdentity | None = None
    candidate_run_id: str | None = None
    comparison: RunComparison | None = None
    efficiency: EfficiencySummary | None = None
    evaluation: PolicyEvaluation | None = None

    @property
    def status(self) -> OutcomeStatus:
        if self.error is not None or self.evaluation is None:
            return "error"
        return "passed" if self.evaluation.passed else "failed"


@dataclass(frozen=True)
class GateReport:
    tier: str
    provider: str
    config_path: str
    policy: GatePolicy
    outcomes: tuple[BenchmarkOutcome, ...]

    @property
    def status(self) -> OutcomeStatus:
        statuses = {outcome.status for outcome in self.outcomes}
        if "error" in statuses:
            return "error"
        return "failed" if "failed" in statuses else "passed"

    @property
    def exit_code(self) -> int:
        """0 passes, 1 is a regression, 2 means the gate could not be evaluated."""
        return {"passed": 0, "failed": 1, "error": 2}[self.status]


def _check_candidate_prompts(
    config: GateConfig, tier: str, candidate_prompts: dict[str, Path]
) -> tuple[str, ...]:
    names = config.tier_benchmarks(tier)
    unknown = sorted(set(candidate_prompts) - set(names))
    if unknown:
        raise GateConfigError(
            f"Candidate prompts name benchmarks outside tier '{tier}': {', '.join(unknown)}"
        )
    return names


def run_gate(
    config: GateConfig,
    *,
    tier: str,
    provider: Provider,
    candidate_prompts: dict[str, Path] | None = None,
    judge_passport: JudgePassport | None = None,
) -> GateReport:
    """Evaluate every benchmark in a tier; one benchmark's error does not hide the others."""
    block = release_gate_block(judge_passport, config.judge)
    if block:
        raise GateConfigError(block)
    overrides = candidate_prompts or {}
    names = _check_candidate_prompts(config, tier, overrides)
    runner = EvaluationRunner(provider)
    outcomes = []
    for name in names:
        spec = config.benchmarks[name]
        prompt_path = overrides.get(name, spec.prompt)
        partial = {
            "benchmark": name,
            "dataset_path": spec.dataset.as_posix(),
            "split": spec.split.value,
            "candidate_prompt_path": prompt_path.as_posix(),
        }
        try:
            dataset = load_jsonl(config.resolve(spec.dataset)).select_split(spec.split)
            prompt = load_prompt(prompt_path if name in overrides else config.resolve(prompt_path))
            snapshot = load_baseline(config.baseline_path(provider.name, name))
            check_baseline_identity(
                snapshot, benchmark=name, provider=provider.name, dataset=dataset
            )
            run = runner.run(dataset, prompt)
            comparison = compare_runs(baseline_run(snapshot, dataset), run)
            efficiency = summarize_efficiency(run)
            outcomes.append(
                BenchmarkOutcome(
                    **partial,
                    baseline=snapshot,
                    candidate_prompt=PromptIdentity(
                        prompt_path.as_posix(), prompt.id, prompt.version, prompt.content_hash
                    ),
                    candidate_run_id=run.id,
                    comparison=comparison,
                    efficiency=efficiency,
                    evaluation=evaluate_policy(comparison, efficiency, config.policy),
                )
            )
        except (ValueError, OSError, ProviderError) as exc:
            outcomes.append(BenchmarkOutcome(**partial, error=str(exc)))
    try:
        config_path = config.source.relative_to(config.resolve(Path("."))).as_posix()
    except ValueError:
        config_path = config.source.as_posix()
    return GateReport(
        tier=tier,
        provider=provider.name,
        config_path=config_path,
        policy=config.policy,
        outcomes=tuple(outcomes),
    )


@dataclass(frozen=True)
class RecordedBaseline:
    benchmark: str
    path: Path
    change: Literal["created", "updated", "unchanged"]
    snapshot: BaselineSnapshot


def record_baselines(
    config: GateConfig, *, tier: str, provider: Provider
) -> tuple[RecordedBaseline, ...]:
    """Run the configured prompts and write snapshots only after every benchmark succeeds."""
    runner = EvaluationRunner(provider)
    pending = []
    for name in config.tier_benchmarks(tier):
        spec = config.benchmarks[name]
        dataset = load_jsonl(config.resolve(spec.dataset)).select_split(spec.split)
        prompt = load_prompt(config.resolve(spec.prompt))
        snapshot = snapshot_from_run(runner.run(dataset, prompt), benchmark=name, prompt=prompt)
        pending.append((name, config.baseline_path(provider.name, name), snapshot))

    recorded = []
    for name, path, snapshot in pending:
        text = snapshot.to_json()
        if not path.exists():
            change = "created"
        elif path.read_text() == text:
            change = "unchanged"
        else:
            change = "updated"
        if change != "unchanged":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        recorded.append(RecordedBaseline(name, path, change, snapshot))
    return tuple(recorded)
