# EvalBench Agent Guide

## Mission

Build EvalBench as a portfolio-quality, reproducible LLM evaluation and regression platform. Prefer measurable behavior, readable code, and evidence-backed engineering decisions over framework novelty.

## Current scope

- Phase 0, Phase 1, and the offline Phase 2 engine are complete; a credentialed provider smoke test remains optional.
- Phase 3 is active: the Inngest event, secured endpoint, validation, generation, scoring, atomic completion, and safe failed-run finalization are implemented.
- Keep all automated tests offline. Do not add LlamaIndex or LangSmith tracing until their planned slice.

## Architecture rules

- Flask routes orchestrate HTTP concerns only; evaluation logic belongs in framework-independent modules.
- All systems under test implement the provider protocol.
- Datasets, prompts, and scorer settings are validated and content-hashed.
- Historical runs are append-only.
- Deterministic scoring is preferred when a property can be checked directly.
- The public demo must never expose a paid, unauthenticated model endpoint.

## Development commands

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
ruff check .
flask --app evalbench:create_app run --debug
python -m evalbench.cli run --split development
```

## Quality expectations

- Add or update tests for every behavior change.
- Keep secrets in environment variables; never commit `.env`.
- Do not fabricate benchmark numbers or resume metrics.
- Preserve offline operation for tests and the seeded demo.
- Explain failures with actionable error messages.
- Keep comments focused on reasoning that is not obvious from the code.

## Definition of done

A phase is complete only when its automated tests pass, its documented local commands work, and its completion criteria in `plan.md` are demonstrably satisfied.
