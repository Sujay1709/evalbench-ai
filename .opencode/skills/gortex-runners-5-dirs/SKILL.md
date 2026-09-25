---
name: gortex-runners-5-dirs
description: "Work in the runners +5 dirs area — 23 symbols across 7 files (65% cohesion)"
---

# runners +5 dirs

23 symbols | 7 files | 65% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/models.py`
- `evalbench/prompts/registry.py`
- `evalbench/providers/base.py`
- `evalbench/runners/evaluation.py`
- `evalbench/runners/generation.py`
- `evalbench/workflows/artifacts.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | format |
| `evalbench/models.py` | ResponseCache |
| `evalbench/prompts/registry.py` | load_prompt, render, PromptDefinition, inputs, path |
| `evalbench/providers/base.py` | prompt, example, generate |
| `evalbench/runners/evaluation.py` | prompt, prompt |
| `evalbench/runners/generation.py` | commit_cache, prompt, generate_or_load_response, GeneratedResponse, example, ... |
| `evalbench/workflows/artifacts.py` | _load_registered_prompt, version, prompt_id, root |

## Connected Communities

- **tests +7 dirs** (4 cross-edges)
- **datasets +2 dirs** (2 cross-edges)
- **tests +4 dirs** (2 cross-edges)
- **judges +6 dirs** (1 cross-edges)
- **comparisons +2 dirs** (1 cross-edges)
- **. +1 dirs · test_strict_response_schema_and…** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-5")
explore(operation:"context", task:"understand runners +5 dirs", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
