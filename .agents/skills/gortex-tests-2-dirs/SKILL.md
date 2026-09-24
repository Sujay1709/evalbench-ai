---
name: gortex-tests-2-dirs
description: "Work in the tests +2 dirs area — 42 symbols across 4 files (84% cohesion)"
---

# tests +2 dirs

42 symbols | 4 files | 84% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `evalbench/judges/calibration.py`
- `tests/test_dataset.py`
- `tests/test_judge_calibration.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | add |
| `evalbench/judges/calibration.py` | CriterionPair, expected_ids, selections, rows, rubric, ... |
| `tests/test_dataset.py` | expected_tags, dataset_id, test_external_samples_include_pinned_provenance, revision, relative_path |
| `tests/test_judge_calibration.py` | test_rejects_rubric_identity_mismatch, rubric, test_pairs_scores_by_criterion_id_and_sorts_results, result_id, test_rejects_duplicate_selection_for_a_result, ... |

## Connected Communities

- **tests +5 dirs** (8 cross-edges)
- **tests +4 dirs** (2 cross-edges)
- **comparisons +2 dirs** (1 cross-edges)
- **tests +7 dirs** (1 cross-edges)
- **judges +3 dirs** (1 cross-edges)
- **judges +6 dirs** (1 cross-edges)
- **. +1 dirs · evalbench.comparisons.compare_s…** (1 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-116")
explore(operation:"context", task:"understand tests +2 dirs", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
