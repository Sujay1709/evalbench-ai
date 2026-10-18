"""End-to-end gate commands against SQLite and the offline mock provider."""

import json
from xml.etree import ElementTree

import pytest
import yaml
from typer.testing import CliRunner

from evalbench.cli import cli
from tests.conftest import PROJECT_ROOT

runner = CliRunner()
KNOWN_BAD = PROJECT_ROOT / "regression" / "fixtures" / "automotive_qa_missing_task.yaml"
KNOWN_BAD_OVERRIDE = f"automotive-development={KNOWN_BAD}"


@pytest.fixture
def env(tmp_path):
    return {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'gate.db'}",
        "LLM_PROVIDER": "mock",
        "GITHUB_ACTIONS": None,
        "GITHUB_STEP_SUMMARY": None,
    }


def flat(output):
    return " ".join(output.split())


def write_config(tmp_path):
    """A one-benchmark config whose baselines live in the test's temporary directory."""
    path = tmp_path / "gate.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "root": str(PROJECT_ROOT),
                "baselines": str(tmp_path / "baselines"),
                "policy": {
                    "max_newly_failing": 0,
                    "mean_score_tolerance": 0.02,
                    "confidence_level": 0.95,
                    "bootstrap_resamples": 1000,
                    "bootstrap_seed": 42,
                },
                "benchmarks": {
                    "automotive-development": {
                        "dataset": "datasets/automotive_qa/v1.jsonl",
                        "prompt": "prompts/automotive_qa/v1.yaml",
                        "split": "development",
                    }
                },
                "tiers": {"smoke": ["automotive-development"]},
            }
        )
    )
    return path


def test_cli_lists_gate_commands():
    result = runner.invoke(cli, ["--help"])

    assert "gate" in result.output
    assert "record-baseline" in result.output


def test_committed_full_tier_passes_against_committed_baselines(env):
    result = runner.invoke(cli, ["gate", "--tier", "full"], env=env)

    assert result.exit_code == 0, result.output
    assert "Gate PASSED (exit 0)" in result.output
    assert "hotpot-holdout" in result.output


def test_known_bad_prompt_fails_only_its_benchmark_and_saves_reports(env, tmp_path):
    json_path = tmp_path / "out" / "gate.json"
    junit_path = tmp_path / "out" / "gate.xml"
    result = runner.invoke(
        cli,
        [
            "gate", "--tier", "standard", "--candidate-prompt", KNOWN_BAD_OVERRIDE,
            "--json-report", str(json_path), "--junit-report", str(junit_path),
        ],
        env=env,
    )

    assert result.exit_code == 1, result.output
    assert "Gate FAILED (exit 1)" in result.output
    assert "::error" not in result.output
    report = json.loads(json_path.read_text())
    assert {item["name"]: item["status"] for item in report["benchmarks"]} == {
        "automotive-development": "failed",
        "adversarial-development": "passed",
        "squad-development": "passed",
        "hotpot-development": "passed",
    }
    degraded = report["benchmarks"][0]
    assert degraded["candidate_prompt"]["version"] == "v1-known-bad"
    failing = [item["example_id"] for item in degraded["examples"] if not item["candidate_passed"]]
    assert failing == ["auto-001", "auto-002", "auto-003"]
    junit = ElementTree.parse(junit_path).getroot()
    assert (junit.get("failures"), junit.get("errors")) == ("5", "0")


def test_github_actions_mode_emits_annotations_and_a_step_summary(env, tmp_path):
    summary_path = tmp_path / "summary.md"
    actions_env = {**env, "GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary_path)}
    result = runner.invoke(cli, ["gate", "--candidate-prompt", KNOWN_BAD_OVERRIDE], env=actions_env)

    assert result.exit_code == 1
    assert "::error title=EvalBench gate%3A automotive-development::3 example(s)" in result.output
    assert "## EvalBench regression gate: FAILED" in summary_path.read_text()

    quiet = runner.invoke(
        cli, ["gate", "--candidate-prompt", KNOWN_BAD_OVERRIDE, "--no-annotations"], env=actions_env
    )
    assert quiet.exit_code == 1
    assert "::error" not in quiet.output


def test_record_then_gate_round_trip_with_a_missing_and_a_stale_baseline(env, tmp_path):
    config = write_config(tmp_path)
    baseline = tmp_path / "baselines" / "mock" / "automotive-development.json"
    record = ["record-baseline", "--tier", "smoke", "--config", str(config)]

    missing = runner.invoke(cli, ["gate", "--config", str(config)], env=env)
    assert missing.exit_code == 2
    assert "record-baseline" in flat(missing.output)

    created = runner.invoke(cli, record, env=env)
    repeated = runner.invoke(cli, record, env=env)
    assert created.exit_code == 0 and "created" in created.output
    assert repeated.exit_code == 0 and "unchanged" in repeated.output
    assert json.loads(baseline.read_text())["prompt_version"] == "v1"

    passing = runner.invoke(cli, ["gate", "--config", str(config)], env=env)
    assert passing.exit_code == 0, passing.output

    stored = json.loads(baseline.read_text())
    baseline.write_text(json.dumps({**stored, "dataset_hash": "0" * 64}))
    json_path = tmp_path / "stale.json"
    stale = runner.invoke(
        cli, ["gate", "--config", str(config), "--json-report", str(json_path)], env=env
    )
    assert stale.exit_code == 2
    assert "is stale" in flat(stale.output)
    assert json.loads(json_path.read_text())["benchmarks"][0]["status"] == "error"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--tier", "nightly"], "Unknown tier 'nightly'"),
        (["--candidate-prompt", "no-separator"], "use BENCHMARK=PATH"),
        (["--candidate-prompt", f"squad-development={KNOWN_BAD}"], "outside tier 'smoke'"),
        (["--config", "missing-gate.yaml"], "Gate config not found"),
    ],
)
def test_unusable_gate_requests_exit_2(env, arguments, message):
    result = runner.invoke(cli, ["gate", *arguments], env=env)

    assert result.exit_code == 2
    assert message in flat(result.output)


def test_known_bad_workflow_keeps_regression_annotations_enabled():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "regression-gate.yml").read_text()
    self_check = workflow.split("Self-check that a known-bad prompt fails the gate", 1)[1]

    assert "automotive_qa_missing_task.yaml" in self_check
    assert "--no-annotations" not in self_check
    assert "expected 1" in self_check
