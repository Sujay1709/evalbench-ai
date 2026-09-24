---
name: gortex-2-dirs-typer
description: "Work in the . +2 dirs · typer area — 65 symbols across 13 files (76% cohesion)"
---

# . +2 dirs · typer

65 symbols | 13 files | 76% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/__init__.py`
- `evalbench/cli.py`
- `external-call::dep:alembic.migration.MigrationContext`
- `external-call::dep:alembic.script.ScriptDirectory`
- `external-call::dep:evalbench.extensions.migrate`
- `external-call::dep:evalbench.providers.build_provider`
- `external-call::dep:flask.Flask`
- `external-call::dep:rich.table.Table`
- `external-call::dep:rich.text.Text`
- `external-call::stdlib:typer`
- `tests/test_cli.py`
- `tests/test_inngest_integration.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | today, fromisoformat, datetime.date |
| `evalbench/__init__.py` | test_config, create_app |
| `evalbench/cli.py` | example_id, execute, prepare_database, run_id, force, ... |
| `external-call::dep:alembic.migration.MigrationContext` | alembic.migration.MigrationContext |
| `external-call::dep:alembic.script.ScriptDirectory` | alembic.script.ScriptDirectory |
| `external-call::dep:evalbench.extensions.migrate` | evalbench.extensions.migrate |
| `external-call::dep:evalbench.providers.build_provider` | evalbench.providers.build_provider |
| `external-call::dep:flask.Flask` | flask.Flask |
| `external-call::dep:rich.table.Table` | rich.table.Table |
| `external-call::dep:rich.text.Text` | rich.text.Text |
| `external-call::stdlib:typer` | typer |
| `tests/test_cli.py` | monkeypatch, test_cli_queue_prepares_run_and_dispatches_minimal_event, tmp_path |
| `tests/test_inngest_integration.py` | test_production_endpoint_rejects_unsigned_invocations, tmp_path, monkeypatch, tmp_path, test_read_only_demo_does_not_expose_inngest_endpoint |

## Entry Points

- `evalbench/cli.py::judge_with_kev`
- `evalbench/cli.py::label_human`
- `evalbench/cli.py::judge_result`
- `evalbench/cli.py::run_evaluation`
- `evalbench/cli.py::queue_evaluation`

## Connected Communities

- **tests +7 dirs** (15 cross-edges)
- **tests +5 dirs** (10 cross-edges)
- **judges +6 dirs** (6 cross-edges)
- **. +3 dirs · execute_kev_decision** (3 cross-edges)
- **workflows +3 dirs** (2 cross-edges)
- **tests +4 dirs** (2 cross-edges)
- **. +2 dirs · _squad_row** (2 cross-edges)
- **. +1 dirs · test_strict_response_schema_and…** (1 cross-edges)
- **workflows +2 dirs** (1 cross-edges)
- **judges +4 dirs** (1 cross-edges)
- **. +2 dirs · uuid4** (1 cross-edges)
- **comparisons +2 dirs** (1 cross-edges)
- **datasets +2 dirs** (1 cross-edges)
- **judges +3 dirs** (1 cross-edges)
- **judges +1 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-13")
explore(operation:"context", task:"understand . +2 dirs · typer", format:"gcx")
relations(operation:"usages", target:{symbol:"evalbench/cli.py::judge_with_kev"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
