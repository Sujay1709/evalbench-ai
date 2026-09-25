---
name: gortex-2-dirs-generate
description: "Work in the . +2 dirs · generate area — 41 symbols across 12 files (79% cohesion)"
---

# . +2 dirs · generate

41 symbols | 12 files | 79% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/providers/base.py`
- `evalbench/providers/factory.py`
- `evalbench/providers/mock.py`
- `evalbench/providers/openai_provider.py`
- `external-call::dep:evalbench.providers.OpenAIProvider`
- `external-call::dep:evalbench.providers.ProviderResponseError`
- `external-call::dep:evalbench.providers.ProviderTransientError`
- `external-call::dep:openai.APITimeoutError`
- `tests/test_inngest_integration.py`
- `tests/test_judge_execution.py`
- `tests/test_openai_provider.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | time.perf_counter, perf_counter |
| `evalbench/providers/base.py` | ProviderResponse, ProviderError, ProviderResponseError, ProviderTransientError |
| `evalbench/providers/factory.py` | build_provider, settings |
| `evalbench/providers/mock.py` | prompt, example, generate |
| `evalbench/providers/openai_provider.py` | prompt, generate, example, OpenAIProvider |
| `external-call::dep:evalbench.providers.OpenAIProvider` | evalbench.providers.OpenAIProvider |
| `external-call::dep:evalbench.providers.ProviderResponseError` | evalbench.providers.ProviderResponseError |
| `external-call::dep:evalbench.providers.ProviderTransientError` | evalbench.providers.ProviderTransientError |
| `external-call::dep:openai.APITimeoutError` | openai.APITimeoutError |
| `tests/test_inngest_integration.py` | prompt, example, example, generate, generate, ... |
| `tests/test_judge_execution.py` | response, FakeClient, __init__, error |
| `tests/test_openai_provider.py` | test_openai_provider_uses_responses_api_and_captures_usage, prices, __init__, test_openai_provider_classifies_timeout_as_transient, FakeResponses, ... |

## Connected Communities

- **tests +7 dirs** (6 cross-edges)
- **tests +5 dirs** (5 cross-edges)
- **. +3 dirs · evalbench.datasets.ScorerSpec** (2 cross-edges)
- **judges +4 dirs** (1 cross-edges)
- **. +3 dirs · execute_kev_decision** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-114")
explore(operation:"context", task:"understand . +2 dirs · generate", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
