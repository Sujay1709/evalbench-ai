---
name: gortex-tests-generate
description: "Work in the tests · generate area — 35 symbols across 2 files (93% cohesion)"
---

# tests · generate

35 symbols | 2 files | 93% cohesion

## When to Use

Use this skill when working on files in:
- `tests/test_inngest_integration.py`
- `tests/test_runner.py`

## Key Files

| File | Symbols |
|------|---------|
| `tests/test_inngest_integration.py` | prompt, prompt, prompt, __init__, generate, ... |
| `tests/test_runner.py` | generate, generate, prompt, example, prompt, ... |

## How to Explore

```
analyze(operation:"communities", id:"community-110")
explore(operation:"context", task:"understand tests · generate", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
