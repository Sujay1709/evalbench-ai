---
name: gortex-comparisons-2-dirs
description: "Work in the comparisons +2 dirs area — 51 symbols across 11 files (79% cohesion)"
---

# comparisons +2 dirs

51 symbols | 11 files | 79% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/comparisons/bootstrap.py`
- `evalbench/comparisons/efficiency.py`
- `evalbench/comparisons/paired.py`
- `evalbench/comparisons/segments.py`
- `external-call::dep:scipy.stats.bootstrap`
- `external-call::stdlib:numpy`
- `tests/test_bootstrap.py`
- `tests/test_cli.py`
- `tests/test_judge_execution.py`
- `tests/test_openai_provider.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | keys, math, items, isclose, values, ... |
| `evalbench/comparisons/bootstrap.py` | seed, PairedBootstrapResult, BootstrapInterval, n_resamples, paired_bootstrap, ... |
| `evalbench/comparisons/efficiency.py` | LeaderboardEntry, runs, build_leaderboards, BenchmarkBoard |
| `evalbench/comparisons/paired.py` | ExampleComparison, compare_runs, run, CompletedRun, _validated_results, ... |
| `evalbench/comparisons/segments.py` | _summarize, SegmentSummary, dimension, SegmentComparison, compare_segments, ... |
| `external-call::dep:scipy.stats.bootstrap` | scipy.stats.bootstrap |
| `external-call::stdlib:numpy` | numpy |
| `tests/test_bootstrap.py` | test_intervals_match_scipy_paired_percentile_reference |
| `tests/test_cli.py` | event, capture_event |
| `tests/test_judge_execution.py` | create, kwargs |
| `tests/test_openai_provider.py` | kwargs, create |

## Entry Points

- `evalbench/comparisons/bootstrap.py::paired_bootstrap`
- `evalbench/comparisons/segments.py::compare_segments`
- `tests/test_bootstrap.py::test_intervals_match_scipy_paired_percentile_reference`

## Connected Communities

- **tests +5 dirs** (3 cross-edges)
- **tests +4 dirs** (3 cross-edges)
- **. +1 dirs · evalbench.comparisons.paired_bo…** (2 cross-edges)
- **. +2 dirs · run_with_usage** (1 cross-edges)
- **judges +4 dirs** (1 cross-edges)
- **judges +6 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-12")
explore(operation:"context", task:"understand comparisons +2 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"evalbench/comparisons/bootstrap.py::paired_bootstrap"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
