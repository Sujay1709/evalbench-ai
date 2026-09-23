# Phase 5: optional local Kev decisions

Kev is a **secondary, non-generative decision model**. It returns an ordinal
0/1/2 score distribution for each grounded-QA rubric criterion, not a cited
explanation. EvalBench stores it in `kev_decision_attempts`, separate from the
OpenAI judge's quote-backed verdicts, human labels, and authoritative
deterministic scores. No Kev output is a release gate. The upstream
[API contract](https://github.com/jaredpalmer/kev#api) defines the score response.

Kev runs in a **separate local Python environment**. Its current installation
requires Python 3.12 or 3.13; do not add its PyTorch/model dependencies to
EvalBench's Python 3.14 virtual environment or commit model weights. Clone
[Kev](https://github.com/jaredpalmer/kev) beside EvalBench, not inside it, and
follow its `uv sync --extra serve` setup. Start the server with a Hub checkpoint
pinned to its full 40-character commit SHA:

```bash
uv run --extra serve python -m kev.serve \
  --run jaredpalmer/kev-4b@MODEL_COMMIT_SHA --port 8009
```

Replace `MODEL_COMMIT_SHA` with an actual Hugging Face commit SHA. If memory is
limited, try a pinned `kev-0.8b` checkpoint instead. The upstream README says
the 4B and 9B variants fit a 32 GB Mac, but that is not a verified measurement
of your machine. The first run downloads the model. Kev binds to `127.0.0.1`
by default and is unauthenticated unless `KEV_API_KEY` is set; never expose the
port publicly. EvalBench refuses any non-loopback `KEV_BASE_URL` and does not
add a web endpoint. See [Kev setup](https://github.com/jaredpalmer/kev#quick-start)
and [server behavior](https://github.com/jaredpalmer/kev#api).

After applying the latest EvalBench migration, create a completed development
run using `datasets/squad_v2/sample_v1.jsonl` and
`prompts/grounded_qa/v1.yaml`. Copy the **full** run ID. From the EvalBench root:

```bash
# No server call or database write.
python -m evalbench.cli judge-kev --run-id RUN_ID \
  --example-id squad-v2-56ddde6b9a695914005b9628 \
  --dataset datasets/squad_v2/sample_v1.jsonl --split development \
  --expected-run jaredpalmer/kev-4b@MODEL_COMMIT_SHA

# Explicitly authorize one local inference after checking the dry run.
python -m evalbench.cli judge-kev --run-id RUN_ID \
  --example-id squad-v2-56ddde6b9a695914005b9628 \
  --dataset datasets/squad_v2/sample_v1.jsonl --split development \
  --expected-run jaredpalmer/kev-4b@MODEL_COMMIT_SHA --execute
```

The adapter first reads `/v1/models` and requires the server-reported `run` to
match `--expected-run` exactly. It then makes at most one `/v1/systemone`
inference. It records the model card (including backend, precision, and
temperature), exact request/hash, raw response, returned score distributions,
status, and request ID. A connection error, wrong checkpoint, or malformed
distribution becomes a recorded failed attempt rather than a fabricated score.
Repeated invocations create separate attempts. This is an **API integration**;
no live checkpoint run or accuracy claim is part of the automated tests.

The expected score is a continuous mean of the 0/1/2 distribution; the modal
score is only the most probable ordinal level. Neither is a measured accuracy
probability. Kev's own documentation warns that option order can affect
answers, so calibration against human labels and permutation testing remain
required before interpretation. [Kev limitations](https://github.com/jaredpalmer/kev#limitations)

Run the offline adapter, CLI, and migration checks:

```bash
.venv/bin/pytest tests/test_kev.py tests/test_migrations.py -q
```
