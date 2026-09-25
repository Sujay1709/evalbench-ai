---
name: gortex-3-dirs-execute-kev-decision
description: "Work in the . +3 dirs · execute_kev_decision area — 69 symbols across 6 files (76% cohesion)"
---

# . +3 dirs · execute_kev_decision

69 symbols | 6 files | 76% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/judges/kev.py`
- `evalbench/models.py`
- `external-call::stdlib:httpx`
- `tests/test_inngest_integration.py`
- `tests/test_kev.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | urlsplit, urllib.parse.urlsplit |
| `evalbench/judges/kev.py` | validate_pinned_run, response, name, expected_run, base_url, ... |
| `evalbench/models.py` | KevDecisionAttempt |
| `external-call::stdlib:httpx` | httpx |
| `tests/test_inngest_integration.py` | handler, CompletionInterruptingStep, handler, step_id, after_handler, ... |
| `tests/test_kev.py` | run, _seed, card_run, app, monkeypatch, ... |

## Entry Points

- `tests/test_kev.py::test_cli_execute_uses_mocked_local_kev_server`
- `tests/test_kev.py::test_cli_dry_run_never_calls_kev`

## Connected Communities

- **tests +7 dirs** (12 cross-edges)
- **tests +4 dirs** (4 cross-edges)
- **judges +6 dirs** (4 cross-edges)
- **comparisons +2 dirs** (3 cross-edges)
- **tests +5 dirs** (3 cross-edges)
- **. +2 dirs · typer** (2 cross-edges)
- **tests +1 dirs · typer.testing.CliRunner** (2 cross-edges)
- **. +2 dirs · uuid4** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-121")
explore(operation:"context", task:"understand . +3 dirs · execute_kev_decision", format:"gcx")
relations(operation:"usages", target:{symbol:"tests/test_kev.py::test_cli_execute_uses_mocked_local_kev_server"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
