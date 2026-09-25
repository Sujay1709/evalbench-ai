---
name: gortex-judges-4-dirs
description: "Work in the judges +4 dirs area — 53 symbols across 10 files (77% cohesion)"
---

# judges +4 dirs

53 symbols | 10 files | 77% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/config.py`
- `evalbench/datasets/huggingface.py`
- `evalbench/datasets/schemas.py`
- `evalbench/judges/contracts.py`
- `evalbench/judges/human_labels.py`
- `evalbench/judges/rubrics.py`
- `evalbench/providers/base.py`
- `evalbench/providers/openai_provider.py`
- `external-call::dep:openai.OpenAI`

## Key Files

| File | Symbols |
|------|---------|
| `` | lower, strip |
| `evalbench/config.py` | validate_production_secret |
| `evalbench/datasets/huggingface.py` | source_offset, spec, _hotpot_context, spec, _normalize_squad_v2, ... |
| `evalbench/datasets/schemas.py` | EvaluationExample |
| `evalbench/judges/contracts.py` | sources, JudgeOutputError, JudgeVerdict, parse_judge_output, normalized_score, ... |
| `evalbench/judges/human_labels.py` | require_nonblank_reason, value |
| `evalbench/judges/rubrics.py` | _nonblank_description, value |
| `evalbench/providers/base.py` | ProviderConfigurationError |
| `evalbench/providers/openai_provider.py` | timeout_seconds, client, input_usd_per_million, __init__, api_key, ... |
| `external-call::dep:openai.OpenAI` | openai.OpenAI |

## Entry Points

- `evalbench/datasets/huggingface.py::_normalize_squad_v2`

## Connected Communities

- **tests +4 dirs** (11 cross-edges)
- **workflows +3 dirs** (3 cross-edges)
- **comparisons +2 dirs** (2 cross-edges)
- **tests +5 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-2")
explore(operation:"context", task:"understand judges +4 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"evalbench/datasets/huggingface.py::_normalize_squad_v2"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
