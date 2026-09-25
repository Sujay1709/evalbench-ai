---
name: gortex-tests-7-dirs
description: "Work in the tests +7 dirs area — 174 symbols across 30 files (78% cohesion)"
---

# tests +7 dirs

174 symbols | 30 files | 78% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/datasets/schemas.py`
- `evalbench/models.py`
- `evalbench/providers/mock.py`
- `evalbench/runners/evaluation.py`
- `evalbench/web/routes.py`
- `evalbench/workflows/failures.py`
- `evalbench/workflows/functions.py`
- `external-call::dep:evalbench.datasets.DatasetSplitError`
- `external-call::dep:evalbench.datasets.load_jsonl`
- `external-call::dep:evalbench.extensions.db`
- `external-call::dep:evalbench.prompts.load_prompt`
- `external-call::dep:evalbench.providers.MockProvider`
- `external-call::dep:evalbench.runners.EvaluationRunner`
- `external-call::dep:sqlalchemy.update`
- `tests/conftest.py`
- `tests/test_app.py`
- `tests/test_cli.py`
- `tests/test_comparison_web.py`
- `tests/test_comparisons.py`
- `tests/test_config.py`
- `tests/test_dataset.py`
- `tests/test_efficiency_web.py`
- `tests/test_human_labels.py`
- `tests/test_inngest_integration.py`
- `tests/test_judge_execution.py`
- `tests/test_kev.py`
- `tests/test_postgres_integration.py`
- `tests/test_runner.py`
- `tests/test_segments.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | uuid.UUID, types.SimpleNamespace, now, uuid4, uuid, ... |
| `evalbench/datasets/schemas.py` | EvaluationSplit |
| `evalbench/models.py` | ExampleResult, EvaluationRun, utc_now, pass_rate |
| `evalbench/providers/mock.py` | MockProvider |
| `evalbench/runners/evaluation.py` | run, EvaluationRunner, correlation_id, correlation_id, prepare_run |
| `evalbench/web/routes.py` | index |
| `evalbench/workflows/failures.py` | app, finalize_evaluation_failure, ctx |
| `evalbench/workflows/functions.py` | app, example_index, checkpoint, app, provider_factory, ... |
| `external-call::dep:evalbench.datasets.DatasetSplitError` | evalbench.datasets.DatasetSplitError |
| `external-call::dep:evalbench.datasets.load_jsonl` | evalbench.datasets.load_jsonl |
| `external-call::dep:evalbench.extensions.db` | evalbench.extensions.db |
| `external-call::dep:evalbench.prompts.load_prompt` | evalbench.prompts.load_prompt |
| `external-call::dep:evalbench.providers.MockProvider` | evalbench.providers.MockProvider |
| `external-call::dep:evalbench.runners.EvaluationRunner` | evalbench.runners.EvaluationRunner |
| `external-call::dep:sqlalchemy.update` | sqlalchemy.update |
| `tests/conftest.py` | tmp_path, migration_app, tmp_path, app, client, ... |
| `tests/test_app.py` | client, app, test_failed_run_detail_displays_accessible_safe_diagnostic, test_dashboard_and_run_detail_display_the_dataset_split, client, ... |
| `tests/test_cli.py` | test_cli_judge_execute_records_one_mocked_request, monkeypatch, monkeypatch, tmp_path, tmp_path, ... |
| `tests/test_comparison_web.py` | DegradedProvider, app, pair |
| `tests/test_comparisons.py` | app, test_persisted_regression_is_identified_without_calls_or_writes |
| `tests/test_config.py` | test_sqlite_test_override_does_not_inherit_hosted_database_options, monkeypatch, tmp_path |
| `tests/test_dataset.py` | test_dataset_hash_is_stable, relative_path, test_external_samples_have_balanced_evaluation_splits, test_dataset_selects_one_split_and_rehashes_the_exact_subset |
| `tests/test_efficiency_web.py` | efficiency_runs, efficiency_runs, app, Degraded, test_historical_unknown_usage_is_not_rendered_as_free, ... |
| `tests/test_human_labels.py` | test_cli_label_human_hides_judge_verdict_and_saves_label, tmp_path, _seed_run, monkeypatch |
| `tests/test_inngest_integration.py` | test_workflow_resumes_around_atomic_completion, app, app, test_event_identifier_validation_does_not_retry_invalid_events, provider, ... |
| `tests/test_judge_execution.py` | FakeResponse, _valid_output, _run, app |
| `tests/test_kev.py` | test_kev_persists_probabilities_without_mutating_primary_scores, app |
| `tests/test_postgres_integration.py` | postgres_app, test_postgres_runner_persists_json_usage_timestamps_and_reuses_cache |
| `tests/test_runner.py` | app, test_prepare_run_persists_queued_identity_without_provider_call, test_runner_rejects_mixed_labels_in_a_selected_dataset, app, test_runner_rejects_unselected_dataset_before_persistence_or_provider_call, ... |
| `tests/test_segments.py` | count, dataset_path, test_real_persisted_dataset_breakdowns_are_read_only, app |

## Entry Points

- `tests/test_inngest_integration.py::test_workflow_generates_and_scores_each_response_in_stable_checkpoints`
- `tests/test_postgres_integration.py::test_postgres_runner_persists_json_usage_timestamps_and_reuses_cache`
- `tests/test_cli.py::test_cli_judge_execute_records_one_mocked_request`
- `tests/test_cli.py::test_cli_judge_dry_run_does_not_create_attempt_or_call_model`
- `tests/test_inngest_integration.py::test_recovery_acceptance_resumes_without_duplicate_calls_or_writes`

## Connected Communities

- **tests +5 dirs** (22 cross-edges)
- **workflows +3 dirs** (12 cross-edges)
- **tests +4 dirs** (7 cross-edges)
- **. +2 dirs · typer** (6 cross-edges)
- **workflows +2 dirs** (5 cross-edges)
- **. +2 dirs · uuid4** (5 cross-edges)
- **. +3 dirs · execute_kev_decision** (5 cross-edges)
- **comparisons +2 dirs** (3 cross-edges)
- **judges +6 dirs** (3 cross-edges)
- **. +1 dirs · test_postgres_fresh_migration_a…** (2 cross-edges)
- **. +1 dirs · run** (2 cross-edges)
- **. +3 dirs · evalbench.datasets.ScorerSpec** (2 cross-edges)
- **. +1 dirs · evalbench.comparisons.compare_s…** (1 cross-edges)
- **runners +5 dirs** (1 cross-edges)
- **tests +1 dirs · typer.testing.CliRunner** (1 cross-edges)
- **. +1 dirs · readiness** (1 cross-edges)
- **. +1 dirs · comparison** (1 cross-edges)
- **. +3 dirs · score_response** (1 cross-edges)
- **. +2 dirs · generate** (1 cross-edges)
- **. +1 dirs · make_run** (1 cross-edges)
- **judges +3 dirs** (1 cross-edges)
- **. +1 dirs · evalbench.comparisons.paired_bo…** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-8")
explore(operation:"context", task:"understand tests +7 dirs", format:"gcx")
relations(operation:"usages", target:{symbol:"tests/test_inngest_integration.py::test_workflow_generates_and_scores_each_response_in_stable_checkpoints"}, format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
