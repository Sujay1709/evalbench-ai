# Evaluation datasets

EvalBench keeps small, reviewable JSONL fixtures in Git so offline tests and portfolio demonstrations remain reproducible. External examples record their original dataset identity, configuration, split, row ID, repository revision, selection offset, retrieval date, source URL, and license.

## Included samples

| Path | Purpose | Size | Source revision |
|---|---|---:|---|
| `automotive_qa/v1.jsonl` | Native infrastructure and automotive-domain smoke test | 5 | Repository-authored fixture |
| `squad_v2/sample_v1.jsonl` | Grounded QA and explicit abstention | 4 | `3ffb306f725f7d2ce8394bc1873b24868140c412` |
| `hotpot_qa/sample_v1.jsonl` | Supporting-fact and multi-hop QA | 4 | `1908d6afbbead072334abe2965f91bd2709910ab` |

The SQuAD v2 and HotpotQA samples are derived from their Hugging Face validation splits and are attributed under CC BY-SA 4.0. See the [SQuAD v2 dataset card](https://huggingface.co/datasets/rajpurkar/squad_v2) and [HotpotQA dataset card](https://huggingface.co/datasets/hotpotqa/hotpot_qa).

## Run the checked-in samples

```bash
python -m evalbench.cli run \
  --dataset datasets/squad_v2/sample_v1.jsonl \
  --prompt prompts/grounded_qa/v1.yaml \
  --split development

python -m evalbench.cli run \
  --dataset datasets/hotpot_qa/sample_v1.jsonl \
  --prompt prompts/grounded_qa/v1.yaml \
  --split development
```

These commands use the deterministic mock provider. Replace `development` with `holdout` only for an explicit milestone evaluation. Mixed-split runs are rejected. The commands validate dataset conversion, prompt rendering, scoring, persistence, and caching; they do not measure a live LLM.

## Import a deterministic streamed sample

Install the runtime dependencies, then provide a full dataset repository commit SHA. The importer streams only far enough to reach the seeded offsets, normalizes the selected rows, validates the resulting EvalBench schema, and records the exact source positions in each row.

```bash
python -m evalbench.cli import-hf \
  --dataset squad-v2 \
  --revision <40-character-dataset-commit-sha> \
  --source-split validation \
  --target-split development \
  --count 10 \
  --seed 42 \
  --scan-limit 1000 \
  --retrieved-at 2026-08-18 \
  --output datasets/generated/squad_v2_dev.jsonl
```

Use `--dataset hotpot-qa` for the HotpotQA `distractor` configuration. Recording `--retrieved-at` makes a later rerun reproduce the same artifact hash; when omitted, it defaults to the current date. The command refuses to replace an existing artifact unless `--force` is supplied. Network access is needed only for imports; evaluation and automated tests remain offline.

## Sampling decisions and limitations

- Selection offsets are deliberately fixed and stored with each example.
- Two SQuAD rows are answerable and two require abstention.
- The compact HotpotQA fixture keeps only the labeled supporting facts. It does not yet preserve distractor passages, so it must not be reported as a full HotpotQA benchmark.
- Some questions were lightly normalized for punctuation or readability. The original source ID and revision are preserved for comparison.
- Token F1 now supports normalized aliases and partial overlap, while answerability scores explicit abstention separately. Supporting-fact recall remains planned.
- Gold answers remain in scorer configuration and are never inserted into the rendered prompt.

The importer uses the Hugging Face `datasets` library in streaming mode, pins revisions, applies deterministic seeded sampling, and emits the same validated schema. Imported bulk data should be cached outside Git unless its license and repository-size impact have been reviewed.
