---
name: gortex-judges-6-dirs
description: "Work in the judges +6 dirs area — 55 symbols across 11 files (68% cohesion)"
---

# judges +6 dirs

55 symbols | 11 files | 68% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/datasets/loader.py`
- `evalbench/judges/execution.py`
- `evalbench/judges/human_labels.py`
- `evalbench/judges/kev.py`
- `evalbench/judges/rubrics.py`
- `evalbench/prompts/registry.py`
- `evalbench/runners/evaluation.py`
- `evalbench/runners/generation.py`
- `evalbench/workflows/functions.py`
- `tests/test_judge_execution.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | hexdigest, sha256, hashlib, dumps |
| `evalbench/datasets/loader.py` | select_split, split, LoadedDataset, examples, _content_hash, ... |
| `evalbench/judges/execution.py` | JudgePreflightError, run_id, example_id, prepare_judgment, PreparedJudgment, ... |
| `evalbench/judges/human_labels.py` | rubric_hash, response, question, _presentation_hash, reference, ... |
| `evalbench/judges/kev.py` | prepared, rubric, PreparedKevDecision, prepared, prepare_kev_decision, ... |
| `evalbench/judges/rubrics.py` | content_hash, path, load_rubric, RubricDefinition, require_unique_criteria |
| `evalbench/prompts/registry.py` | content_hash |
| `evalbench/runners/evaluation.py` | dataset, dataset |
| `evalbench/runners/generation.py` | prompt, dataset_hash, value, example, provider_name, ... |
| `evalbench/workflows/functions.py` | _scoring_step_id, example_id, example_id, _generation_step_id |
| `tests/test_judge_execution.py` | app, app, prepared, test_preflight_rejects_wrong_split_and_changed_fixture_before_client, prepared |

## Connected Communities

- **tests +7 dirs** (6 cross-edges)
- **tests +4 dirs** (2 cross-edges)
- **judges +4 dirs** (2 cross-edges)
- **tests +5 dirs** (2 cross-edges)
- **. +1 dirs · test_strict_response_schema_and…** (1 cross-edges)
- **. +1 dirs · evalbench.comparisons.paired_bo…** (1 cross-edges)
- **datasets +2 dirs** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-85")
explore(operation:"context", task:"understand judges +6 dirs", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
