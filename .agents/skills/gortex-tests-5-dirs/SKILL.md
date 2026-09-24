---
name: gortex-tests-5-dirs
description: "Work in the tests +5 dirs area — 69 symbols across 16 files (63% cohesion)"
---

# tests +5 dirs

69 symbols | 16 files | 63% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/config.py`
- `evalbench/datasets/schemas.py`
- `evalbench/judges/human_labels.py`
- `evalbench/models.py`
- `evalbench/runners/aggregation.py`
- `external-call::dep:evalbench.datasets.DatasetProvenance`
- `external-call::stdlib:pytest`
- `tests/conftest.py`
- `tests/test_aggregation.py`
- `tests/test_comparison_web.py`
- `tests/test_config.py`
- `tests/test_dataset.py`
- `tests/test_efficiency.py`
- `tests/test_human_labels.py`
- `tests/test_judge_execution.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | fullmatch, os, get |
| `evalbench/config.py` | to_flask_config, database_flask_config, Settings |
| `evalbench/datasets/schemas.py` | DatasetProvenance |
| `evalbench/judges/human_labels.py` | HumanLabelError, record_human_labels, HumanCriterionRating, ratings, presentation, ... |
| `evalbench/models.py` | HumanLabelSet |
| `evalbench/runners/aggregation.py` | aggregate_example_scores, results, AggregationError, AggregateMetrics |
| `external-call::dep:evalbench.datasets.DatasetProvenance` | evalbench.datasets.DatasetProvenance |
| `external-call::stdlib:pytest` | pytest |
| `tests/conftest.py` | postgres_app |
| `tests/test_aggregation.py` | test_aggregate_example_scores_rejects_an_empty_run, invalid_score, test_aggregate_example_scores_rejects_invalid_values, test_aggregate_example_scores_calculates_pass_count_and_mean |
| `tests/test_comparison_web.py` | unexpected_call, args |
| `tests/test_config.py` | test_sqlite_does_not_receive_postgres_pool_options, test_hosted_postgres_rejects_weaker_tls, sslmode, test_configuration_errors_do_not_echo_database_credentials, query, ... |
| `tests/test_dataset.py` | test_dataset_provenance_requires_a_complete_https_url, test_dataset_reports_when_requested_split_is_missing, source_url, tmp_path |
| `tests/test_efficiency.py` | test_price_configuration_requires_both_prices |
| `tests/test_human_labels.py` | test_invalid_or_incomplete_human_labels_are_not_persisted, app, test_human_labels_are_independent_append_only_and_content_bound, annotation, _ratings, ... |
| `tests/test_judge_execution.py` | model_dump, kwargs |

## Entry Points

- `tests/test_human_labels.py::test_invalid_or_incomplete_human_labels_are_not_persisted`
- `tests/conftest.py::postgres_app`
- `tests/test_human_labels.py::test_human_labels_are_independent_append_only_and_content_bound`

## Connected Communities

- **tests +7 dirs** (10 cross-edges)
- **versions +2 dirs** (4 cross-edges)
- **tests +4 dirs** (4 cross-edges)
- **. +1 dirs · evalbench.comparisons.paired_bo…** (2 cross-edges)
- **. +2 dirs · uuid4** (2 cross-edges)
- **. +2 dirs · typer** (1 cross-edges)
- **judges +6 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-108")
explore(operation:"context", task:"understand tests +5 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"tests/test_human_labels.py::test_invalid_or_incomplete_human_labels_are_not_persisted"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
