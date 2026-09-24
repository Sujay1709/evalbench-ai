---
name: gortex-3-dirs-score-response
description: "Work in the . +3 dirs · score_response area — 32 symbols across 5 files (81% cohesion)"
---

# . +3 dirs · score_response

32 symbols | 5 files | 81% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/scorers/deterministic.py`
- `evalbench/workflows/failures.py`
- `external-call::stdlib:unicodedata`
- `tests/test_cli.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | json, sub, split, Counter, strip, ... |
| `evalbench/scorers/deterministic.py` | ScoreResult, score_response, candidate, _normalize_qa_text, spec, ... |
| `evalbench/workflows/failures.py` | parse_serialized_original_event, value |
| `external-call::stdlib:unicodedata` | unicodedata |
| `tests/test_cli.py` | fail_once, tmp_path, monkeypatch, test_cli_queue_reuses_run_when_dispatch_is_retried, event |

## Entry Points

- `evalbench/scorers/deterministic.py::score_response`
- `tests/test_cli.py::test_cli_queue_reuses_run_when_dispatch_is_retried`

## Connected Communities

- **judges +4 dirs** (3 cross-edges)
- **workflows +3 dirs** (2 cross-edges)
- **comparisons +2 dirs** (2 cross-edges)
- **tests +7 dirs** (2 cross-edges)
- **. +1 dirs · test_strict_response_schema_and…** (1 cross-edges)
- **. +2 dirs · typer** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-92")
explore(operation:"context", task:"understand . +3 dirs · score_response", format:"gcx")
relations(operation:"usages", target:{symbol:"evalbench/scorers/deterministic.py::score_response"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
