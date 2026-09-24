# EvalBench Agent Guide

## Mission

Build EvalBench as a portfolio-quality, reproducible LLM evaluation and regression platform. Prefer measurable behavior, readable code, and evidence-backed engineering decisions over framework novelty.

## Current scope

- Phase 0, Phase 1, and the offline Phase 2 engine are complete; a credentialed provider smoke test remains optional.
- Phase 3 is complete: the secured Inngest workflow, queue command, durable checkpoints, failure finalization, local trace workflow, and recovery acceptance coverage are implemented.
- Phase 4 implementation is merged in PR #20, and browser acceptance passed on September 21, 2026; see `docs/phase-4-acceptance.md` before Phase 5 model-judge work begins.
- The secure Supabase/PostgreSQL infrastructure interlude merged in PR #21; SQLite remains the offline default. No hosted provisioning or data transfer is implicit.
- Phase 5 has advisory judge contracts, opt-in single-result execution, blind local human labels, and an optional loopback-only Kev decision adapter; agreement calibration and any model-based release decision remain unimplemented.
- React/Vite and shadcn are approved as a separate frontend migration after Phase 5 rubric/output contracts, before annotation UX. Preserve Jinja until tested feature parity; do not initialize shadcn at the Flask root.
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
INNGEST_DEV=1 python -m evalbench.cli queue --split development
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

<!-- gortex:communities:start -->
## Community Skills

| Area | Description | Explore |
|------|-------------|---------|
| Tests 7 Dirs | 174 symbols | `analyze(operation:"communities", id:"community-8")` |
| Tests 4 Dirs | 72 symbols | `analyze(operation:"communities", id:"community-3")` |
| 3 Dirs Execute Kev Decision | 69 symbols | `analyze(operation:"communities", id:"community-121")` |
| Tests 5 Dirs | 69 symbols | `analyze(operation:"communities", id:"community-108")` |
| 2 Dirs Typer | 65 symbols | `analyze(operation:"communities", id:"community-13")` |
| Judges 6 Dirs | 55 symbols | `analyze(operation:"communities", id:"community-85")` |
| Judges 4 Dirs | 53 symbols | `analyze(operation:"communities", id:"community-2")` |
| Comparisons 2 Dirs | 51 symbols | `analyze(operation:"communities", id:"community-12")` |
| Workflows 3 Dirs | 46 symbols | `analyze(operation:"communities", id:"community-6")` |
| Tests 2 Dirs | 42 symbols | `analyze(operation:"communities", id:"community-116")` |
| 2 Dirs Generate | 41 symbols | `analyze(operation:"communities", id:"community-114")` |
| Tests Generate | 35 symbols | `analyze(operation:"communities", id:"community-110")` |
| 3 Dirs Score Response | 32 symbols | `analyze(operation:"communities", id:"community-92")` |
| Evalbench Extensions Db | 31 symbols | `analyze(operation:"communities", id:"community-37")` |
| 2 Dirs Uuid4 | 24 symbols | `analyze(operation:"communities", id:"community-115")` |
| Runners 5 Dirs | 23 symbols | `analyze(operation:"communities", id:"community-5")` |
| Judges 3 Dirs | 22 symbols | `analyze(operation:"communities", id:"community-119")` |
| Sqlalchemy | 21 symbols | `analyze(operation:"communities", id:"community-93")` |
| Versions 2 Dirs | 20 symbols | `analyze(operation:"communities", id:"community-15")` |
| 1 Dirs Test Strict Response Schema And | 20 symbols | `analyze(operation:"communities", id:"community-117")` |

<!-- gortex:communities:end -->
