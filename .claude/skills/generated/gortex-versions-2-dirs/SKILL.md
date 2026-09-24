---
name: gortex-versions-2-dirs
description: "Work in the versions +2 dirs area — 20 symbols across 11 files (94% cohesion)"
---

# versions +2 dirs

20 symbols | 11 files | 94% cohesion

## When to Use

Use this skill when working on files in:
- `external-call::dep:alembic.op`
- `external-call::stdlib:sqlalchemy`
- `migrations/versions/a3e6d9c2f750_add_kev_decision_attempts.py`
- `migrations/versions/aab0bf3b7b5b_create_evaluation_tables.py`
- `migrations/versions/b7d93a12e640_add_result_usage.py`
- `migrations/versions/c8e2d4f61a90_add_dataset_split_to_evaluation_runs.py`
- `migrations/versions/d4c7a2b9f610_add_judge_attempts.py`
- `migrations/versions/e6b4c8d912af_add_run_error_category.py`
- `migrations/versions/f2e8c1d7a640_add_human_label_sets.py`
- `migrations/versions/f4a9c2d713be_add_run_correlation_id.py`
- `tests/test_migrations.py`

## Key Files

| File | Symbols |
|------|---------|
| `external-call::dep:alembic.op` | alembic.op |
| `external-call::stdlib:sqlalchemy` | sqlalchemy |
| `migrations/versions/a3e6d9c2f750_add_kev_decision_attempts.py` | downgrade, upgrade |
| `migrations/versions/aab0bf3b7b5b_create_evaluation_tables.py` | upgrade, downgrade |
| `migrations/versions/b7d93a12e640_add_result_usage.py` | upgrade, downgrade |
| `migrations/versions/c8e2d4f61a90_add_dataset_split_to_evaluation_runs.py` | downgrade, upgrade |
| `migrations/versions/d4c7a2b9f610_add_judge_attempts.py` | downgrade, upgrade |
| `migrations/versions/e6b4c8d912af_add_run_error_category.py` | upgrade, downgrade |
| `migrations/versions/f2e8c1d7a640_add_human_label_sets.py` | upgrade, downgrade |
| `migrations/versions/f4a9c2d713be_add_run_correlation_id.py` | downgrade, upgrade |
| `tests/test_migrations.py` | migration_app, test_run_metadata_migrations_backfill_and_require_new_fields |

## Entry Points

- `migrations/versions/aab0bf3b7b5b_create_evaluation_tables.py::upgrade`
- `tests/test_migrations.py::test_run_metadata_migrations_backfill_and_require_new_fields`
- `migrations/versions/d4c7a2b9f610_add_judge_attempts.py::upgrade`
- `migrations/versions/a3e6d9c2f750_add_kev_decision_attempts.py::upgrade`
- `migrations/versions/f2e8c1d7a640_add_human_label_sets.py::upgrade`

## Connected Communities

- **tests +7 dirs** (6 cross-edges)
- **. +1 dirs · test_postgres_fresh_migration_a…** (4 cross-edges)
- **tests +5 dirs** (2 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-15")
explore(operation:"context", task:"understand versions +2 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"migrations/versions/aab0bf3b7b5b_create_evaluation_tables.py::upgrade"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
