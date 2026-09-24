---
name: gortex-1-dirs-test-strict-response-schema-and
description: "Work in the . +1 dirs · test_strict_response_schema_and… area — 20 symbols across 9 files (79% cohesion)"
---

# . +1 dirs · test_strict_response_schema_and…

20 symbols | 9 files | 79% cohesion

## When to Use

Use this skill when working on files in:
- ``
- `external-call::dep:evalbench.judges.RubricDefinition`
- `external-call::dep:evalbench.judges.judge_response_format`
- `external-call::dep:evalbench.judges.load_rubric`
- `external-call::dep:evalbench.judges.parse_judge_output`
- `external-call::dep:jsonschema.Draft202012Validator`
- `external-call::dep:jsonschema.validate`
- `external-call::stdlib:yaml`
- `tests/test_judge_contracts.py`

## Key Files

| File | Symbols |
|------|---------|
| `` | update |
| `external-call::dep:evalbench.judges.RubricDefinition` | evalbench.judges.RubricDefinition |
| `external-call::dep:evalbench.judges.judge_response_format` | evalbench.judges.judge_response_format |
| `external-call::dep:evalbench.judges.load_rubric` | evalbench.judges.load_rubric |
| `external-call::dep:evalbench.judges.parse_judge_output` | evalbench.judges.parse_judge_output |
| `external-call::dep:jsonschema.Draft202012Validator` | jsonschema.Draft202012Validator |
| `external-call::dep:jsonschema.validate` | jsonschema.validate |
| `external-call::stdlib:yaml` | yaml |
| `tests/test_judge_contracts.py` | change, message, test_strict_response_schema_and_parsed_verdict, valid_output, test_rubric_has_stable_content_hash_independent_of_yaml_key_order, ... |

## Connected Communities

- **tests +5 dirs** (4 cross-edges)
- **judges +6 dirs** (4 cross-edges)

## How to Explore

```
analyze(operation:"communities", id:"community-117")
explore(operation:"context", task:"understand . +1 dirs · test_strict_response_schema_and…", format:"gcx")
```

_`format: "gcx"` returns the [GCX1 compact wire format](../../docs/wire-format.md) — round-trippable, ~27% fewer tokens than JSON. Drop it for JSON output; agents using `@gortex/wire` or the Go `github.com/gortexhq/gcx-go` package decode either._
