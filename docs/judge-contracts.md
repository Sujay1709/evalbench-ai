# Phase 5: judge contracts (first slice)

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
Existing deterministic scorers remain authoritative. This slice makes no model
calls, stores no judge grades, and does not add a release gate. Next slices must
capture raw responses and model/prompt identities, handle refusals and incomplete
outputs, compare repeated and order-swapped judgments with human labels, and
report agreement and failure modes before any operational use.

Run the contract checks locally with
`.venv/bin/pytest tests/test_judge_contracts.py -q`. They are offline and require
neither an OpenAI key nor a database.
