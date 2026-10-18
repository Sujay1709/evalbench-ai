"""CI regression gate: committed baselines, versioned policy, and machine-readable reports."""

from evalbench.gates.baseline import BaselineError, BaselineSnapshot, load_baseline
from evalbench.gates.config import GateConfig, GateConfigError, GatePolicy, load_gate_config
from evalbench.gates.policy import GateCheck, PolicyEvaluation, evaluate_policy
from evalbench.gates.reports import github_annotations, json_report, junit_report, step_summary
from evalbench.gates.runner import (
    BenchmarkOutcome,
    GateReport,
    RecordedBaseline,
    record_baselines,
    run_gate,
)
from evalbench.gates.sampler import AdaptiveSampleAudit, audit_adaptive_sample

__all__ = [
    "AdaptiveSampleAudit",
    "BaselineError",
    "BaselineSnapshot",
    "BenchmarkOutcome",
    "GateCheck",
    "GateConfig",
    "GateConfigError",
    "GatePolicy",
    "GateReport",
    "PolicyEvaluation",
    "RecordedBaseline",
    "audit_adaptive_sample",
    "evaluate_policy",
    "github_annotations",
    "json_report",
    "junit_report",
    "load_baseline",
    "load_gate_config",
    "record_baselines",
    "run_gate",
    "step_summary",
]
