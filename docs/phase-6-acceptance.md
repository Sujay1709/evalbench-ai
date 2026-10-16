# Phase 6 CI acceptance

Phase 6 is complete only when, on real GitHub Actions, a known regression
produces a non-zero exit code, a useful CI annotation, and a saved comparison
report (`plan.md`, Phase 6 "Done when").

## Acceptance record — October 15, 2026

**Result: passed.** Both runs used `.github/workflows/regression-gate.yml` with
the offline mock provider and a throwaway SQLite database on `ubuntu-latest`.
No model API calls were made and no secrets were used.

### Passing change: PR #34

[Run 38836359204](https://github.com/Sujay1709/evalbench-ai/actions/runs/38836359204)
gated [PR #34](https://github.com/Sujay1709/evalbench-ai/pull/34), which
introduced the gate (commit `70a1088`).

- The standard tier passed with exit 0 against the committed baselines.
- The known-bad self-check step ran the smoke tier with
  `regression/fixtures/automotive_qa_missing_task.yaml`. It printed
  `Gate FAILED (exit 1)` with `auto-001`, `auto-002`, and `auto-003` newly
  failing, and the step passed because it expects exit 1.
- The `regression-gate-reports` artifact (4,522 bytes) was uploaded.

### Regressed change: PR #35 (closed, not merged)

[Run 38839572119](https://github.com/Sujay1709/evalbench-ai/actions/runs/38839572119)
gated the throwaway draft
[PR #35](https://github.com/Sujay1709/evalbench-ai/pull/35), which removed the
`Task: {question}` line from `prompts/automotive_qa/v1.yaml`.

- **Non-zero exit:** the "Gate candidate against committed baselines" step
  failed with exit code 1, and the job concluded `failure`.
- **Annotations:** GitHub recorded two failure annotations titled
  `EvalBench gate: automotive-development`:
  - `3 example(s) passed in the baseline and fail now (allowed 0): auto-001, auto-002, auto-003`
  - `Mean score delta -1.000, 95% paired interval [-1.000, -1.000], tolerance 0.020: the interval supports a regression`
- **Saved report:** the `regression-gate-reports` artifact (4,836 bytes) with
  JSON and JUnit reports was uploaded.
- The self-check step still passed, and the other development benchmarks were
  unaffected.

The PR was closed without merging and its branch deleted after the run was
recorded.

### Observations

- The runner warned that `actions/checkout@v4`, `actions/setup-python@v5`, and
  `actions/upload-artifact@v4` target the deprecated Node.js 20 runtime and
  were forced onto Node.js 24. The run was unaffected; upgrading the actions
  is a follow-up.
- Evidence is limited to mock-provider baselines and two- or three-example
  fixture benchmarks, as described in [regression-gate.md](regression-gate.md).
