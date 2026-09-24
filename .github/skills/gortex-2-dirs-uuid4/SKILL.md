---
name: gortex-2-dirs-uuid4
description: "Work in the . +2 dirs · uuid4 area — 24 symbols across 6 files (72% cohesion)"
---

# . +2 dirs · uuid4

24 symbols | 6 files | 72% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/workflows/events.py`
- `evalbench/workflows/functions.py`
- `external-call::dep:evalbench.workflows.EvaluationRunRequestedData`
- `tests/test_inngest_integration.py`
- `tests/test_workflow_events.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | uuid.uuid4, uuid4 |
| `evalbench/workflows/events.py` | EvaluationRunRequestedData |
| `evalbench/workflows/functions.py` | validate_event_identifiers, _parse_request, ctx, ctx, app, ... |
| `external-call::dep:evalbench.workflows.EvaluationRunRequestedData` | evalbench.workflows.EvaluationRunRequestedData |
| `tests/test_inngest_integration.py` | test_workflow_validation_rejects_unknown_run_without_retry, test_workflow_validation_is_a_persisted_idempotent_step, test_workflow_validation_short_circuits_completed_run, app, app, ... |
| `tests/test_workflow_events.py` | field, test_evaluation_run_requested_rejects_unexpected_or_sensitive_data, test_evaluation_run_requested_builds_a_minimal_inngest_event, test_evaluation_run_requested_rejects_invalid_identifiers |

## Entry Points

- `tests/test_inngest_integration.py::test_workflow_validation_is_a_persisted_idempotent_step`

## Connected Communities

- **tests +7 dirs** (11 cross-edges)
- **tests +5 dirs** (4 cross-edges)
- **workflows +3 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-115")
explore(operation:"context", task:"understand . +2 dirs · uuid4", format:"gcx")
relations(operation:"usages", target:{symbol:"tests/test_inngest_integration.py::test_workflow_validation_is_a_persisted_idempotent_step"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
