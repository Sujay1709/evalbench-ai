"""Versioned regression-gate configuration: policy thresholds, benchmarks, and tiers."""

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from evalbench.datasets import EvaluationSplit

# Benchmark names become baseline file names, so keep them path-safe.
BenchmarkName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]


class GateConfigError(ValueError):
    """The gate configuration cannot be loaded or is internally inconsistent."""


class GatePolicy(BaseModel):
    """Thresholds are operator policy; they are recorded with every report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_newly_failing: int = Field(ge=0)
    mean_score_tolerance: float = Field(ge=0, le=1)
    confidence_level: float = Field(gt=0, lt=1)
    bootstrap_resamples: int = Field(ge=100, le=100_000)
    bootstrap_seed: int = Field(ge=0)
    max_p95_latency_ms: float | None = Field(default=None, gt=0)
    max_estimated_cost_usd: float | None = Field(default=None, ge=0)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


class BenchmarkSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: Path
    prompt: Path
    split: EvaluationSplit


class GateConfig(BaseModel):
    """`root` is relative to the config file; every other relative path is relative to root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    root: Path = Path(".")
    baselines: Path = Path("baselines")
    policy: GatePolicy
    benchmarks: dict[BenchmarkName, BenchmarkSpec] = Field(min_length=1)
    tiers: dict[BenchmarkName, list[BenchmarkName]] = Field(min_length=1)
    source: Path = Field(default=Path("gate.yaml"), exclude=True)

    @model_validator(mode="after")
    def validate_tiers(self) -> "GateConfig":
        for tier, names in self.tiers.items():
            if not names:
                raise ValueError(f"Tier '{tier}' must list at least one benchmark")
            if len(set(names)) != len(names):
                raise ValueError(f"Tier '{tier}' lists a benchmark more than once")
            unknown = sorted(set(names) - self.benchmarks.keys())
            if unknown:
                raise ValueError(f"Tier '{tier}' references unknown benchmarks: {unknown}")
        return self

    def resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.source.parent / self.root / path).resolve()

    def tier_benchmarks(self, tier: str) -> tuple[str, ...]:
        if tier not in self.tiers:
            raise GateConfigError(
                f"Unknown tier '{tier}'; choose one of: {', '.join(sorted(self.tiers))}"
            )
        return tuple(self.tiers[tier])

    def baseline_path(self, provider: str, benchmark: str) -> Path:
        return self.resolve(self.baselines) / provider / f"{benchmark}.json"


def load_gate_config(path: str | Path) -> GateConfig:
    config_path = Path(path).resolve()
    if not config_path.is_file():
        raise GateConfigError(f"Gate config not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as exc:
        raise GateConfigError(f"Gate config is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateConfigError("Gate config must be a YAML mapping")
    try:
        return GateConfig.model_validate({**raw, "source": config_path})
    except ValidationError as exc:
        raise GateConfigError(f"Invalid gate config {config_path}: {exc}") from exc
