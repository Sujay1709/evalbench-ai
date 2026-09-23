# Phase 5: independent human labels

Human labels are the comparison point for testing an LLM judge. They are not
derived from the judge's output. The `label-human` command shows a completed
grounded-QA result's question, context, reference (or unanswerable status),
candidate response, and versioned rubric anchors. It deliberately does **not**
show the judge verdict or deterministic score while the annotator rates it.

After applying the latest Alembic migration, run this from the project root:

```bash
python -m evalbench.cli label-human --run-id RUN_ID \
  --example-id squad-v2-56ddde6b9a695914005b9628 \
  --dataset datasets/squad_v2/sample_v1.jsonl --split development \
  --annotator-id reviewer_01
```

Use the full run ID printed by `python -m evalbench.cli run`. The CLI asks for
one 0/1/2 score and a short reason per rubric criterion. Use a pseudonymous
annotator ID, not a name or email. The command is local-only, makes no model
calls, and is disabled when `DEMO_READ_ONLY=true`. It verifies the completed
run, exact dataset hash/split and stored input before presenting an example.

Each complete submission creates a new `human_label_sets` row with the result
ID, rubric ID/version/hash, pseudonymous annotator ID, all criterion ratings,
and a hash of the exact displayed evidence. A repeat submission creates a
second row rather than rewriting the first. Later calibration must explicitly
choose which submission(s) to compare; duplicates are **not** silently averaged.

These records do not change deterministic run scores or existing judge
attempts. The CLI does not prove that a label is correct or that annotators
agree. Human-label agreement statistics, a disagreement queue, adversarial
examples, and a calibrated release policy remain later Phase 5 work. A React
annotation UI is also separate, after read-only frontend migration acceptance.

The database may contain private evaluation inputs and responses. Protect it
accordingly; no public labeling endpoint or authentication scheme is added here.

Offline checks:

```bash
.venv/bin/pytest tests/test_human_labels.py tests/test_migrations.py -q
```
