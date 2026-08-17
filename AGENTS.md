# EvalBench Agent Guide

## Mission

Build EvalBench as a portfolio-quality, reproducible LLM evaluation and regression platform. Prefer measurable behavior, readable code, and evidence-backed engineering decisions over framework novelty.

## Current scope

- Phase 0: Flask foundation, typed configuration, persistence, health checks, tests, and local tooling.
- Phase 1: versioned automotive JSONL data, prompt registry, offline provider, deterministic scoring, persisted runs, and response caching.
- Do not add real model calls, LlamaIndex, LangSmith tracing, or Inngest workflows until their planned phase.

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
python -m evalbench.cli run
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
