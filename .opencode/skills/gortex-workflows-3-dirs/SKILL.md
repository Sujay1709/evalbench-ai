---
name: gortex-workflows-3-dirs
description: "Work in the workflows +3 dirs area — 46 symbols across 6 files (71% cohesion)"
---

# workflows +3 dirs

46 symbols | 6 files | 71% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/providers/base.py`
- `evalbench/runners/evaluation.py`
- `evalbench/workflows/artifacts.py`
- `evalbench/workflows/failures.py`
- `evalbench/workflows/functions.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | join |
| `evalbench/providers/base.py` | Provider |
| `evalbench/runners/evaluation.py` | __init__, provider |
| `evalbench/workflows/artifacts.py` | run, EvaluationArtifacts, project_root, load_run_artifacts |
| `evalbench/workflows/failures.py` | FailureCategory, SerializedFailureError, _classify_failure, non_retriable_failure, category, ... |
| `evalbench/workflows/functions.py` | provider_factory, _validate_generation_checkpoint, _build_verified_provider, app, app, ... |

## Connected Communities

- **tests +7 dirs** (9 cross-edges)
- **comparisons +2 dirs** (5 cross-edges)
- **. +3 dirs · score_response** (2 cross-edges)
- **runners +5 dirs** (2 cross-edges)
- **datasets +2 dirs** (1 cross-edges)
- **. +2 dirs · load_segments** (1 cross-edges)
- **. +1 dirs · run** (1 cross-edges)
- **workflows +2 dirs** (1 cross-edges)
- **tests +5 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-6")
explore(operation:"context", task:"understand workflows +3 dirs", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
