---
name: gortex-judges-3-dirs
description: "Work in the judges +3 dirs area — 22 symbols across 5 files (66% cohesion)"
---

# judges +3 dirs

22 symbols | 5 files | 66% cohesion

## When to Use

Use this skill when working on files in:
- `evalbench/judges/contracts.py`
- `evalbench/judges/execution.py`
- `evalbench/models.py`
- `external-call::dep:openai.OpenAIError`
- `tests/test_judge_execution.py`

## Key Files

| File | Symbols |
|------|---------|
| `evalbench/judges/contracts.py` | rubric, judge_response_format |
| `evalbench/judges/execution.py` | execute_judgment, model, prepared, timeout_seconds, rubric, ... |
| `evalbench/models.py` | JudgeAttempt |
| `external-call::dep:openai.OpenAIError` | openai.OpenAIError |
| `tests/test_judge_execution.py` | test_success_persists_advisory_evidence_without_mutating_run, app, test_provider_error_is_recorded_without_sensitive_exception_text, app, app, ... |

## Entry Points

- `tests/test_judge_execution.py::test_success_persists_advisory_evidence_without_mutating_run`

## Connected Communities

- **tests +7 dirs** (5 cross-edges)
- **judges +4 dirs** (3 cross-edges)
- **. +2 dirs · uuid4** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-119")
explore(operation:"context", task:"understand judges +3 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"tests/test_judge_execution.py::test_success_persists_advisory_evidence_without_mutating_run"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
