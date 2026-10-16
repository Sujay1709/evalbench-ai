# Regression gate

`evalbench gate` reruns a tier of benchmarks with the configured provider and
compares each run, example by example, with a committed baseline. It answers
one question for a pull request: did this change make a known-good behavior
worse?

## Configuration

[`regression/gate.yaml`](../regression/gate.yaml) is versioned with the code.

| Section | Meaning |
|---|---|
| `benchmarks` | Named dataset, prompt, and split combinations |
| `tiers` | `smoke` (one development benchmark), `standard` (all development benchmarks, the CI default), `full` (adds holdout) |
| `policy` | The thresholds below; its SHA-256 is recorded in every report |
| `baselines` | Directory of `<provider>/<benchmark>.json` snapshots |

CI tiers use development splits only. Run `full` deliberately, because
repeatedly gating on holdout examples turns them into development data.

## Policy

A benchmark **fails** (exit code 1) when either check fails:

1. **Newly failing examples.** More than `max_newly_failing` examples (default
   0) that passed in the baseline fail now. This is the hard requirement and
   lists the example IDs.
2. **Mean score.** The mean score drops by more than `mean_score_tolerance`
   *and* the paired bootstrap interval (`confidence_level`, seeded) excludes
   zero. A drop past the tolerance whose interval includes zero passes with a
   note, because the evidence does not support a regression.

`max_p95_latency_ms` and `max_estimated_cost_usd` are optional budgets. Unknown
cost fails a cost budget. P95 latency is skipped when every response came from
the cache. A failed provider call fails its examples, so errors surface
through the newly-failing check.

The gate **cannot be evaluated** (exit code 2) when the config, tier, or
candidate prompt is invalid; a baseline is missing; a baseline is stale
(benchmark, provider, dataset name, version, split, or content hash differ);
or the provider fails before a run completes. Exit code 2 takes precedence
over exit code 1.

## Reports

| Output | Option | Contents |
|---|---|---|
| Console table | always | Status, mean delta, newly failing count, and run ID per benchmark |
| JSON | `--json-report PATH` | Policy and hash, baseline and candidate prompt identities, summary, bootstrap interval and warnings, efficiency, checks, and per-example deltas |
| JUnit XML | `--junit-report PATH` | One suite per benchmark; each check and example is a testcase, with only newly failing examples marked as failures |
| GitHub annotations | `--annotations` (default when `GITHUB_ACTIONS=true`) | One `::error` line per failed check, plus a Markdown table in `GITHUB_STEP_SUMMARY` |

Candidate runs are stored like any other run, so the run ID in a report opens
in the dashboard drill-down.

## Testing a prompt change

```bash
python -m evalbench.cli gate --tier standard \
  --candidate-prompt automotive-development=prompts/automotive_qa/v2.yaml
```

Overrides must name a benchmark in the selected tier. Without overrides the
gate uses the configured prompts, so editing a configured prompt file in a pull
request gates that edit directly.

## Updating baselines

```bash
python -m evalbench.cli record-baseline --tier full
```

This runs every benchmark first and writes nothing if any fails. It then
reports each file as created, updated, or unchanged. A baseline update
redefines expected behavior, so review it like code and explain it in the pull
request.

## Known-bad fixture

[`regression/fixtures/automotive_qa_missing_task.yaml`](../regression/fixtures/automotive_qa_missing_task.yaml)
drops the `{question}` line from the automotive prompt. The mock provider
abstains with `insufficient evidence` when a prompt omits an example's
question or context, which models a real failure: a model cannot answer a
question it never received. The workflow re-runs this fixture after the main
gate and fails if it does not exit 1, so a gate that silently stops detecting
regressions is caught.

Local verification on October 15, 2026, with the mock provider and SQLite:

| Command | Exit | Result |
|---|---|---|
| `gate --tier standard` | 0 | All four development benchmarks passed |
| `gate --tier standard --candidate-prompt automotive-development=<fixture>` | 1 | Only `automotive-development` failed: `auto-001`, `auto-002`, and `auto-003` newly failing; mean delta -1.000 |

## Limits

- Baselines exist only for the offline mock provider. The gate detects prompt
  and pipeline regressions, not live-model drift. Live baselines need a
  credentialed run and a decision about repeated-call variability.
- Benchmarks hold two or three examples. Bootstrap intervals at that size carry
  small-sample warnings and rarely exclude zero, so the newly-failing check
  does most of the work. Larger cohorts are needed before the mean-score check
  means much.
- Model-based judge scores are not gated; Phase 5's reliability claim is open.
- Acceptance requires a real GitHub Actions run of
  `.github/workflows/regression-gate.yml` showing the annotation and the
  uploaded `regression-gate-reports` artifact.
