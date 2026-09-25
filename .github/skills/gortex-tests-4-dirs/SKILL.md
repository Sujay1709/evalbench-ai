---
name: gortex-tests-4-dirs
description: "Work in the tests +4 dirs area — 72 symbols across 10 files (75% cohesion)"
---

# tests +4 dirs

72 symbols | 10 files | 75% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/database.py`
- `evalbench/judges/kev.py`
- `evalbench/providers/usage.py`
- `external-call::dep:sqlalchemy.engine.make_url`
- `tests/test_app.py`
- `tests/test_comparison_web.py`
- `tests/test_efficiency_web.py`
- `tests/test_health.py`
- `tests/test_inngest_integration.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | isfinite, get |
| `evalbench/database.py` | pool_timeout, ssl_root_cert, pool_size, max_overflow, database_config, ... |
| `evalbench/judges/kev.py` | KevResponseError, _model_card, rubric, _ratings, payload, ... |
| `evalbench/providers/usage.py` | usage_snapshot, metadata |
| `external-call::dep:sqlalchemy.engine.make_url` | sqlalchemy.engine.make_url |
| `tests/test_app.py` | test_homepage_loads, client |
| `tests/test_comparison_web.py` | query, test_filter_and_navigation, client, client, size, ... |
| `tests/test_efficiency_web.py` | client, client, test_leaderboard_and_pareto_table_are_read_only, client, efficiency_runs, ... |
| `tests/test_health.py` | client, test_readiness, test_liveness, client |
| `tests/test_inngest_integration.py` | client, app, test_development_app_serves_registered_inngest_function |

## Connected Communities

- **tests +7 dirs** (4 cross-edges)
- **comparisons +2 dirs** (3 cross-edges)
- **. +1 dirs · evalbench.comparisons.paired_bo…** (1 cross-edges)
- **. +1 dirs · make_run** (1 cross-edges)
- **datasets +2 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-3")
explore(operation:"context", task:"understand tests +4 dirs", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
