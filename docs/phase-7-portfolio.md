# Phase 7 measured notes

These notes are for a recruiter, a resume line, and a technical interview. Every
number below comes from a command or a GitHub Actions run on October 18, 2026.
They describe the offline mock provider and the fixture datasets. They are not
a live-model benchmark and not a human-calibration result.

## What was measured

Local smoke gate, mock provider, SQLite:

```text
evalbench gate --tier smoke
Gate PASSED (exit 0)
automotive-development  mean delta +0.000  newly failing 0
```

`demo-seed` then created five development runs and no holdout runs:

| Run | Passing |
|---|---|
| `automotive-development` (`d9a2ba99`) | 3/3 |
| `adversarial-development` (`34cffa12`) | 2/2 |
| `squad-development` (`dc1d7b7d`) | 2/2 |
| `hotpot-development` (`f0e34069`) | 2/2 |
| `automotive-development:known-bad` (`32fef060`) | 0/3 |

The read-only demo was started with `DEMO_READ_ONLY=true` and the mock
provider. `scripts/smoke_demo.sh http://127.0.0.1:8000` printed
`Demo smoke test passed`. The home page links to the comparison of `d9a2ba99`
and `32fef060` filtered to regressions. That page reported:

- Mean score delta **-1.000** (1.000 → 0.000) across 3 paired examples.
- Pass-rate change **-100.0** percentage points (100.0% → 0.0%).
- **3** score regressions: `auto-001`, `auto-002`, and `auto-003`. 3 newly
  failing, 0 newly passing.
- 95% paired bootstrap interval **-1.000 to -1.000** for both the mean and the
  median, from 10,000 resamples, seed 42, PCG64, NumPy 2.5.4, linear quantiles.
- The page also prints the small-sample warning (fewer than 30 pairs) and that
  identical deltas make a zero-width interval not a certainty.
- Generation-equivalent cost **$0.000000** on both runs. The first seed
  generated 3/3 responses (0 cache hits) at 0.00 ms median generation latency.

GitHub Actions, still the mock provider:

- [Regression gate run 39176061699](https://github.com/Sujay1709/evalbench-ai/actions/runs/39176061699)
  passed the standard tier (exit 0), showed annotations for the same three
  automotive failures and a mean delta of -1.000, and uploaded
  `regression-gate-reports`.
- [Container smoke test run 39175853230](https://github.com/Sujay1709/evalbench-ai/actions/runs/39175853230)
  succeeded on `main` for the research-slices push. That is the latest
  container run on `main` as of this note. Render itself has not been created.

Screenshots of this local demo are `docs/images/demo-home.png` and
`docs/images/demo-regression.png`.

## Recruiter version

EvalBench is a regression harness for LLM prompts. A public demo mode replays
saved offline runs and refuses writes, so a visitor can inspect a caught
failure without an API key. In the seeded demo, dropping the question from the
automotive prompt turns 3 passing answers into 3 failures and moves the mean
score from 1.000 to 0.000. The same check runs in GitHub Actions and fails the
job only when that known-bad prompt stops exiting 1.

## Resume version

Built an offline LLM evaluation harness with versioned datasets, deterministic
scorers, append-only runs, and a CI gate. A known-bad prompt fixture fails the
gate with 3 newly failing examples and a mean-score delta of -1.000; the
read-only demo shows that comparison without calling a model.

## Technical version

The gate pairs each example with its baseline. It fails on any newly failing
example, and on a mean-score drop past the configured tolerance when the paired
bootstrap interval excludes zero. The automotive known-bad case trips both
checks because every example delta is -1. The interval is therefore zero-width.
The UI says that is not certainty, and the benchmarks are smaller than 30
pairs, so the newly-failing check is the one that generalizes. Baselines exist
only for the mock provider. A judge cannot enter this gate unless a passport
supplies holdout agreement, repeatability, stable order swaps, and a verbosity
probe. No measured judge-human kappa is in the repository, so no judge is
authorized.

## Still open

- No Render service has been created, so a public URL has not passed
  `scripts/smoke_demo.sh`.
- The October 13, 2026 labeling session stored 3 assisted holdout labels
  against a workbench minimum of 10, with no opted-in judge. That is not a
  reliability claim.
