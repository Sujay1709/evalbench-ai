# Phase 5: judge contracts and bounded execution

The first Phase 5 slice defines **what a judge may return**, not whether a model
judge is trustworthy yet. A rubric is a versioned YAML file with 0/1/2 anchors for
each criterion. EvalBench validates it, computes a canonical content hash, and
binds that identity to every parsed verdict. Changing any anchor changes the
hash even if the human-readable version was not updated; a changed rubric should
also receive a new version before real calibration data is collected.

`rubrics/grounded_qa/v1.yaml` assesses answer quality and evidence alignment for
grounded QA. The contract accepts JSON containing exactly one assessment per
criterion, with an integer score, evidence source, exact quote, and reason.
Missing/duplicate criteria, out-of-range scores, extra fields, fabricated quotes,
and malformed JSON are rejected. Quotes can come from the supplied context,
reference answer, or candidate response; `none` requires an empty quote. Quote
source `none` is allowed only with score 0. Positive scores need cited text. Quote
matching proves only that the cited text exists, **not** that the judge's
interpretation or score is correct.

The response format follows [OpenAI's strict Structured Outputs
requirements](https://developers.openai.com/api/docs/guides/structured-outputs):
every field is required and objects reject additional properties. The local
parser applies stricter rubric-specific checks because a schema cannot guarantee
that every criterion appears exactly once or that a quoted span really exists.

```python
from pathlib import Path

from evalbench.judges import judge_response_format, load_rubric, parse_judge_output

rubric = load_rubric(Path("rubrics/grounded_qa/v1.yaml"))
response_format = judge_response_format(rubric)  # strict JSON Schema for a future adapter
verdict = parse_judge_output(
    raw_json,
    rubric=rubric,
    example_id="example-1",
    sources={"context": context, "reference": reference, "response": candidate},
)
```

The normalized score is an **advisory** equal-weight mean of criterion scores.
Existing deterministic scorers remain authoritative. The execution slice adds a
single-result CLI with an explicit `--execute` opt-in; it does not add a release gate.
It accepts only completed runs and grounded-QA examples with a context, question,
and reference or unanswerable label. Run ID, dataset hash/split, and stored input
must all match before an API client is created. The automotive fixture has no
context, so use the SQuAD v2 or HotpotQA samples here.

```bash
# After migrations, create a completed offline run and copy its full Run ID.
python -m evalbench.cli run --dataset datasets/squad_v2/sample_v1.jsonl \
  --prompt prompts/grounded_qa/v1.yaml --split development

# Preview without a key, API call, or judge record.
python -m evalbench.cli judge --run-id RUN_ID \
  --example-id squad-v2-56ddde6b9a695914005b9628 \
  --dataset datasets/squad_v2/sample_v1.jsonl --split development

# Optional paid call: set OPENAI_API_KEY in your untracked .env first.
python -m evalbench.cli judge --run-id RUN_ID \
  --example-id squad-v2-56ddde6b9a695914005b9628 \
  --dataset datasets/squad_v2/sample_v1.jsonl --split development \
  --judge-model YOUR_AVAILABLE_MODEL --execute
```

Each execution makes at most one Responses API request, with 768 output tokens,
30-second default timeout, zero SDK retries, strict structured output, and
`store=False`. This caps request count and output, **not dollar cost**; check
current model pricing before opting in. The entire request text and provider
response are stored locally in `judge_attempts`, alongside rubric/prompt hashes,
model, outcome, and validated assessments. Failed, refused, incomplete, and
invalid responses are recorded too. Treat this table as potentially sensitive:
datasets, candidate answers, and judge output may contain private content.
The CLI is disabled for execution in `DEMO_READ_ONLY` mode and no paid web
endpoint is exposed.

Future slices must compare repeated and order-swapped judgments with human
labels, and report agreement and failure modes before operational use.

Run the offline checks from the project root (copy only the line inside the block):

```bash
.venv/bin/pytest tests/test_judge_contracts.py tests/test_judge_execution.py -q
```

The execution tests use a fake client and never require an OpenAI key.
