"""JSON, JUnit XML, GitHub annotation, and step-summary renderings of a gate report."""

import json
from dataclasses import asdict
from typing import Any
from xml.etree import ElementTree

from evalbench.gates.runner import BenchmarkOutcome, GateReport


def _benchmark_dict(outcome: BenchmarkOutcome) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": outcome.benchmark,
        "status": outcome.status,
        "dataset_path": outcome.dataset_path,
        "split": outcome.split,
        "candidate_prompt_path": outcome.candidate_prompt_path,
        "error": outcome.error,
    }
    if outcome.status == "error":
        return entry
    baseline, comparison = outcome.baseline, outcome.comparison
    bootstrap = outcome.evaluation.bootstrap
    entry.update(
        dataset={
            "name": baseline.dataset_name,
            "version": baseline.dataset_version,
            "hash": baseline.dataset_hash,
        },
        baseline_prompt={
            "id": baseline.prompt_id,
            "version": baseline.prompt_version,
            "hash": baseline.prompt_hash,
        },
        candidate_prompt={
            "id": outcome.candidate_prompt.id,
            "version": outcome.candidate_prompt.version,
            "hash": outcome.candidate_prompt.content_hash,
        },
        prompt_changed=baseline.prompt_hash != outcome.candidate_prompt.content_hash,
        candidate_run_id=outcome.candidate_run_id,
        summary={
            "examples": len(comparison.examples),
            "baseline_mean_score": comparison.baseline_mean_score,
            "candidate_mean_score": comparison.candidate_mean_score,
            "mean_score_delta": comparison.mean_score_delta,
            "baseline_pass_rate": comparison.baseline_pass_rate,
            "candidate_pass_rate": comparison.candidate_pass_rate,
            "pass_rate_delta": comparison.pass_rate_delta,
            "improved": comparison.improved,
            "regressed": comparison.regressed,
            "unchanged": comparison.unchanged,
            "newly_passing": comparison.newly_passing,
            "newly_failing": comparison.newly_failing,
        },
        bootstrap=None
        if bootstrap is None
        else {
            "confidence_level": bootstrap.confidence_level,
            "n_resamples": bootstrap.n_resamples,
            "seed": bootstrap.seed,
            "mean_delta": asdict(bootstrap.mean_delta),
            "median_delta": asdict(bootstrap.median_delta),
            "warnings": list(bootstrap.warnings),
        },
        efficiency=asdict(outcome.efficiency),
        checks=[asdict(check) for check in outcome.evaluation.checks],
        examples=[asdict(example) for example in comparison.examples],
    )
    return entry


def report_dict(report: GateReport) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": report.status,
        "exit_code": report.exit_code,
        "tier": report.tier,
        "provider": report.provider,
        "config": {
            "path": report.config_path,
            "policy": report.policy.model_dump(mode="json"),
            "policy_hash": report.policy.content_hash,
        },
        "benchmarks": [_benchmark_dict(outcome) for outcome in report.outcomes],
    }


def json_report(report: GateReport, branch: dict[str, str] | None = None) -> str:
    payload = report_dict(report)
    if branch:
        payload["branch"] = branch
    return json.dumps(payload, indent=2) + "\n"


def junit_report(report: GateReport) -> str:
    """One testsuite per benchmark: policy checks plus one testcase per example."""
    suites = ElementTree.Element("testsuites", name=f"evalbench-gate-{report.tier}")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for outcome in report.outcomes:
        suite = ElementTree.SubElement(suites, "testsuite", name=outcome.benchmark)
        counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        if outcome.status == "error":
            counts["errors"] += 1
            error = ElementTree.SubElement(
                _testcase(suite, outcome.benchmark, "gate"),
                "error",
                message=outcome.error or "error",
            )
            error.text = outcome.error
        else:
            for check in outcome.evaluation.checks:
                testcase = _testcase(suite, f"{outcome.benchmark}.checks", check.name)
                if check.status == "failed":
                    counts["failures"] += 1
                    ElementTree.SubElement(testcase, "failure", message=check.message)
                elif check.status == "skipped":
                    counts["skipped"] += 1
                    ElementTree.SubElement(testcase, "skipped", message=check.message)
                else:
                    ElementTree.SubElement(testcase, "system-out").text = check.message
            for example in outcome.comparison.examples:
                testcase = _testcase(suite, f"{outcome.benchmark}.examples", example.example_id)
                detail = (
                    f"baseline {example.baseline_score:.3f} -> "
                    f"candidate {example.candidate_score:.3f} ({example.change})"
                )
                if example.baseline_passed and not example.candidate_passed:
                    counts["failures"] += 1
                    failure = ElementTree.SubElement(
                        testcase, "failure", message="Passed in the baseline; fails now"
                    )
                    failure.text = detail
                else:
                    ElementTree.SubElement(testcase, "system-out").text = detail
        counts["tests"] = len(suite)
        for key, value in counts.items():
            suite.set(key, str(value))
            totals[key] += value
    for key, value in totals.items():
        suites.set(key, str(value))
    ElementTree.indent(suites)
    return ElementTree.tostring(suites, encoding="unicode", xml_declaration=True) + "\n"


def _testcase(suite: ElementTree.Element, classname: str, name: str) -> ElementTree.Element:
    return ElementTree.SubElement(suite, "testcase", classname=classname, name=name)


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def github_annotations(report: GateReport) -> list[str]:
    """Single-line workflow commands; GitHub parses them from the step log."""
    lines = []
    for outcome in report.outcomes:
        title = _escape_property(f"EvalBench gate: {outcome.benchmark}")
        if outcome.status == "error":
            lines.append(f"::error title={title}::{_escape_data(outcome.error or 'error')}")
            continue
        for check in outcome.evaluation.checks:
            if check.status == "failed":
                lines.append(f"::error title={title}::{_escape_data(check.message)}")
    return lines


def step_summary(report: GateReport, branch: dict[str, str] | None = None) -> str:
    lines = [
        f"## EvalBench regression gate: {report.status.upper()}",
        "",
    ]
    if branch and branch.get("base_ref") and branch.get("head_ref"):
        sha = branch.get("head_sha", "")
        short = sha[:7] if sha else "unknown"
        lines.append(
            f"Branch `{branch['head_ref']}` compared with `{branch['base_ref']}` at `{short}`."
        )
        lines.append("")
    lines += [
        f"Tier `{report.tier}`, provider `{report.provider}`, policy "
        f"`{report.policy.content_hash[:12]}`.",
        "",
        "| Benchmark | Status | Mean score delta | Newly failing |",
        "| --- | --- | ---: | ---: |",
    ]
    for outcome in report.outcomes:
        if outcome.status == "error":
            lines.append(f"| {outcome.benchmark} | error | n/a | n/a |")
            continue
        comparison = outcome.comparison
        lines.append(
            f"| {outcome.benchmark} | {outcome.status} | {comparison.mean_score_delta:+.3f} | "
            f"{comparison.newly_failing} |"
        )
    problems = [
        f"- **{outcome.benchmark}:** {message}"
        for outcome in report.outcomes
        for message in (
            [outcome.error]
            if outcome.status == "error"
            else [check.message for check in outcome.evaluation.checks if check.status == "failed"]
        )
    ]
    if problems:
        lines += ["", "### Problems", "", *problems]
    return "\n".join(lines) + "\n"
