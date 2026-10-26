# EvalBench Deployment Guide

> **Status: deployment files implemented; not yet deployed.** The Docker image, `render.yaml` Blueprint, idempotent `demo-seed` command, read-only guard, and container smoke test exist and run in CI. A production read-only process now refuses to boot unless `LLM_PROVIDER=mock` and `MAX_RUN_COST_USD=0`, and it trusts one Render proxy hop. No Render service has been created yet, so the release checks in Sections 8 and 13 remain open.

## 1. Purpose

This document defines how EvalBench will move from a local Flask project to a safe public portfolio demo on Render. The deployment must be:

- reproducible from the repository;
- testable before release;
- safe to expose publicly;
- unable to spend a recruiter's or developer's LLM credits;
- observable through lightweight health endpoints; and
- honest about free-host limitations.

The repository root is:

```text
/Users/sujaygopal/MyProjects/Project Eval Bench
```

## 2. Deployment Model

EvalBench will support two operating modes.

### Local full mode

Used by the developer to create datasets, run evaluations, call an optional LLM provider, label examples, and write results.

```text
DEMO_READ_ONLY=false
```

### Public demo mode

Used for the recruiter-facing Render deployment. It loads precomputed demonstration runs and allows visitors to explore results, but disables dataset uploads, evaluation execution, labels, and other mutations.

```text
DEMO_READ_ONLY=true
```

This separation is important because a public evaluation endpoint could otherwise become an unauthenticated proxy for paid model calls.

## 3. Deployment Files

| File | Responsibility |
|---|---|
| `requirements.txt` | Runtime dependencies installed into the image. |
| `.env.example` | Documented environment-variable names with no secrets. |
| `Dockerfile` | Production image: non-root user, demo defaults, seed then Gunicorn on `$PORT`. |
| `.dockerignore` | Excludes local databases, caches, secrets, reports, and editor/agent folders. |
| `render.yaml` | Render Blueprint: free Docker web service, `/health/ready` check, generated `SECRET_KEY`. |
| `evalbench/__init__.py` | Flask application factory, `create_app()`. |
| `evalbench/demo.py` | Idempotent demo seed and the featured regression pair. |
| `evalbench/security.py` | Read-only write guard and baseline security headers. |
| `scripts/smoke_demo.sh` | HTTP smoke test for any running demo, local or on Render. |
| `.github/workflows/container.yml` | Builds the image, starts it, and runs the smoke test in CI. |
| `tests/test_demo.py` | Offline tests for seeding, readiness, the guard, and the home-page link. |

This guide must be updated if implementation changes any of these names.

## 4. Environment Variables

The final `.env.example` should document at least the following variables:

| Variable | Local default | Render value | Secret? |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | No |
| `DEMO_READ_ONLY` | `false` | `true` | No |
| `DATABASE_URL` | SQLite development URL | Seeded demo database or managed Postgres URL | Sometimes |
| `SECRET_KEY` | Developer-generated value | Render-generated value | Yes |
| `LOG_LEVEL` | `DEBUG` | `INFO` | No |
| `LLM_PROVIDER` | `mock` or opt-in `openai` | `mock` | No |
| `OPENAI_API_KEY` | Optional local value | **Do not set for the public demo** | Yes |
| `OPENAI_MODEL` | `gpt-5.6-luna` | Unused in mock mode | No |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Unused in mock mode | No |
| `OPENAI_MAX_RETRIES` | `2` | Unused in mock mode | No |
| `OPENAI_MAX_OUTPUT_TOKENS` | `128` | Unused in mock mode | No |
| `MAX_RUN_COST_USD` | Small local budget | `0` in public demo mode | No |
| `INNGEST_DEV` | `1` when using the local Dev Server | Unset | No |
| `INNGEST_APP_ID` | `evalbench` | `evalbench` | No |
| `INNGEST_EVENT_KEY` | Not needed with the Dev Server | Required only for hosted workflows | Yes |
| `INNGEST_SIGNING_KEY` | Not needed with the Dev Server | Required only for hosted workflows | Yes |

Rules:

- Never commit `.env` or a real provider key.
- Never place a secret directly in `render.yaml`.
- Never include Inngest keys, LLM keys, or sensitive dataset content in workflow events.
- The application must fail closed if `DEMO_READ_ONLY=true` but a mutation endpoint is called.
- Production configuration must reject debug mode.
- A production read-only demo must refuse to boot when `LLM_PROVIDER` is anything other than `mock` or when `MAX_RUN_COST_USD` is not `0`. That is the public demo, and it must not be able to call a paid model.

## 5. Local Pre-deployment Checks

Run these checks only after their files and commands have been implemented.

### Verified local durable workflow

The Phase 3 workflow can be exercised without Inngest Cloud or a paid model. Use three terminals from the repository root.

Terminal 1 — Flask and the registered Inngest endpoint:

```bash
source .venv/bin/activate
INNGEST_DEV=1 flask --app evalbench:create_app run --debug --port 5000
```

Terminal 2 — local Dev Server and trace UI:

```bash
npx --ignore-scripts=false inngest-cli@latest dev \
  --no-discovery \
  -u http://127.0.0.1:5000/api/inngest
```

Terminal 3 — prepare a queued run and dispatch its identifier-only event:

```bash
curl --fail --request PUT http://127.0.0.1:5000/api/inngest
source .venv/bin/activate
INNGEST_DEV=1 python -m evalbench.cli queue --split development
```

The sync response should contain `"ok": true`. Open `http://localhost:8288`, confirm that `evalbench-eval-run` is registered, locate the event ID printed by the queue command, and inspect its step trace. The event contains only `run_id` and `correlation_id`; provider keys, prompts, and dataset rows remain in application-owned storage.

For a deterministic recovery exercise, select a `generate-response-*` trace step and choose **Rerun from step**. Confirm the new trace completes, then inspect the same EvalBench run and verify it still has exactly three unique example results. The automated acceptance test additionally interrupts execution after one generation checkpoint and verifies resume behavior without duplicate model calls or database writes.

If dispatch fails before a response is received, use the printed correlation ID to retry the same queued identity instead of creating another run:

```bash
INNGEST_DEV=1 python -m evalbench.cli queue \
  --split development \
  --correlation-id <CORRELATION_ID>
```

### Native Python demo

This reproduces the public demo without Docker. It uses a throwaway SQLite file
so it never touches the database configured in `.env`:

```bash
source .venv/bin/activate
export DATABASE_URL=sqlite:///demo.db LLM_PROVIDER=mock  # instance/demo.db
python -m evalbench.cli demo-seed
APP_ENV=production DEMO_READ_ONLY=true MAX_RUN_COST_USD=0 \
  SECRET_KEY="$(openssl rand -hex 32)" \
  gunicorn --bind 127.0.0.1:8000 'evalbench:create_app()'
```

`demo-seed` refuses to run unless `LLM_PROVIDER=mock`. Running it again reports
every run as `exists` instead of creating duplicates, because each seeded run
uses a correlation ID derived from its dataset and prompt hashes.

### Container workflow

The `Container smoke test` workflow builds and checks the image on every
relevant pull request. To repeat it on a machine with Docker:

```bash
docker build -t evalbench:local .
docker run --rm -p 8000:10000 -e PORT=10000 \
  -e SECRET_KEY="$(openssl rand -hex 32)" evalbench:local
```

Do not pass `--env-file .env`; the local `.env` may point at a hosted database
or contain a provider key, and the demo needs neither.

### Required smoke checks

In another terminal:

```bash
scripts/smoke_demo.sh http://127.0.0.1:8000
```

The script checks liveness, demo-aware readiness, security headers, the
home-page link to the featured regression, the regression report itself, and
that a `POST` is rejected with `403`.

Before deployment, also verify:

- the complete test suite passes;
- the production container starts without development dependencies;
- seeded demo data loads more than once without duplication;
- public demo mode blocks every write and evaluation-run action;
- the site does not display secrets, hidden holdout labels, stack traces, or local paths;
- static assets load correctly behind HTTPS; and
- the dashboard works on desktop and mobile widths.

## 6. Production Process Contract

The web service runs Flask behind Gunicorn. The image's start command is:

```bash
python -m evalbench.cli demo-seed && exec gunicorn --bind 0.0.0.0:${PORT} --threads 4 --timeout 120 --access-logfile - 'evalbench:create_app()'
```

Gunicorn reads its worker count from `WEB_CONCURRENCY`: the image defaults to
`2`, and `render.yaml` sets `1` for the free plan's 0.1 CPU and 512 MB. If the
seed fails, the container exits before Gunicorn starts, so Render never routes
traffic to an empty demo.

Why Gunicorn is needed:

- Flask's development server is not designed for internet-facing production traffic.
- Gunicorn manages worker processes, timeouts, and graceful shutdown.
- Render supplies the `PORT` environment variable that the service must bind to.

The worker and timeout values are starting assumptions, not permanent tuning values. They must be tested against Render memory limits and observed request latency.

## 7. Health Endpoint Design

### `GET /health`

This is a **liveness** endpoint. It answers whether the Flask process can receive a request.

Requirements:

- return HTTP `200` and a small JSON body;
- perform no LLM call or expensive query;
- expose no version, secret, stack trace, or internal host information;
- remain accessible without login; and
- be explicitly exempted from mutation-only protections.

### `GET /health/ready`

This is a **readiness** endpoint. It answers whether the application is ready to serve the demo.

It may verify only essential dependencies, such as a fast database query and the presence of seeded demo data. It must return a non-success status when the app cannot serve its primary experience.

Implemented behavior: readiness always checks the database. When
`DEMO_READ_ONLY=true` it also requires every seeded demo run and returns `503`
with `"demo_data": "missing"` until they exist.

### Read-only guard

In demo mode, a `before_request` hook rejects every method other than `GET`,
`HEAD`, and `OPTIONS` with `403` before routing, including unknown paths and
`/api/inngest`. New write endpoints are therefore blocked by default rather than
by remembering to decorate them.

### Important Flask clarification

Declaring `/health` before other route functions does not automatically bypass authentication or rate-limiting middleware. The application will explicitly allow the health blueprint or endpoint in those policies. This makes the behavior testable rather than dependent on source-file order.

### Inngest endpoint

Full mode will expose a signed `/api/inngest` endpoint so Inngest can invoke registered evaluation workflows. This endpoint is not a health endpoint and must verify Inngest signatures in production. The public read-only demo does not need to trigger hosted evaluation workflows.

## 8. Render Deployment Procedure

Do not perform these steps until the implementation, tests, and project plan are approved.

### Step 1: Prepare the Git repository

1. Review the diff and confirm no secrets or local databases are tracked.
2. Run tests and the production container smoke test.
3. Push the approved repository to GitHub.
4. Choose a stable release commit for deployment.

### Step 2: Review `render.yaml`

The repository's [`render.yaml`](render.yaml) defines one free Docker web
service, `evalbench-demo`, that builds the same `Dockerfile` CI smoke-tests. It
sets `APP_ENV=production`, `DEMO_READ_ONLY=true`, `LLM_PROVIDER=mock`,
`MAX_RUN_COST_USD=0`, and `WEB_CONCURRENCY=1`; Render generates `SECRET_KEY`.
`autoDeployTrigger: checksPass` deploys a new commit only after its GitHub
checks pass. It declares no database, disk, or provider key: the container seeds
its own SQLite file on every start.

### Step 3: Create the Render service

1. In the Render Dashboard choose **New > Blueprint** and connect the GitHub repository.
2. Confirm the plan shows **Free** and the service name `evalbench-demo`.
3. Review every environment variable before the first deployment; none should be a provider key.
4. Confirm the health-check path is `/health/ready`.
5. Deploy and wait for the first deploy to report **Live**.

### Step 4: Verify the release

Replace `<service-name>` with the actual Render service name:

```bash
scripts/smoke_demo.sh https://<service-name>.onrender.com
```

The first request after inactivity may take close to a minute while the free
instance starts. Then manually verify:

- the homepage loads over HTTPS;
- the seeded leaderboard and run comparison appear;
- an individual regression can be opened;
- write controls are absent or disabled;
- a direct request to a mutation endpoint is rejected server-side;
- error pages do not expose debug information; and
- Render logs contain no secret or full sensitive prompt data.

## 9. Optional UptimeRobot Monitor

Render currently spins down a free web service after 15 minutes without inbound HTTP requests or WebSocket messages. A free UptimeRobot monitor can request `/health` every five minutes, reducing inactivity-related cold starts.

Configure it only after the final Render URL works:

1. Create or sign in to an UptimeRobot account.
2. Add an HTTP(S) monitor.
3. Use a descriptive name such as `EvalBench Portfolio Demo`.
4. Set the URL to `https://<service-name>.onrender.com/health`.
5. Select the five-minute interval available on the free plan.
6. Add an email alert contact if desired.
7. Create the monitor and confirm the first successful response.

This is an external monitoring check, not a service-level agreement. It does not prevent downtime caused by deployments, restarts, platform maintenance, exhausted quotas, or application failures. Keeping a free instance active also consumes Render free-instance hours.

Current platform references:

- [Render free web service limitations](https://render.com/docs/free)
- [Render health checks](https://render.com/docs/health-checks)
- [Render uptime practices](https://render.com/docs/uptime-best-practices)
- [UptimeRobot monitoring intervals](https://help.uptimerobot.com/en/articles/11360876-what-is-a-monitoring-interval-in-uptimerobot)

## 10. Data Persistence Strategy

### Implemented PostgreSQL connection contract

The database integration supports Supabase through SQLAlchemy and psycopg while
retaining SQLite locally. See [the Supabase guide](docs/supabase-database.md) for
verified TLS, per-process pool limits, migration/runtime role separation, Data API
protection, and migration tests. No hosted project has been provisioned or
smoke-tested. Configure `DATABASE_SSL_ROOT_CERT` to a certificate file available
inside the deployment, never a Mac-only path. Use the direct or Session pooler
endpoint, not the transaction pooler. Apply Alembic migrations with a migration
role before starting the runtime backend; runtime CLI commands do not create
PostgreSQL tables. Public demos should use separate SELECT-only credentials.

Switching the URL does not transfer SQLite history. Preserve existing data and
plan any data transfer separately. The public demo image deliberately ignores
this path and seeds a local SQLite file instead.

The first public demo should favor reliability and cost control over hosted write capability.

- Seed precomputed, non-sensitive results during startup.
- Make seed operations idempotent so restarts do not duplicate records.
- Treat the public demo database as reconstructable.
- Do not use the container filesystem for irreplaceable user data.
- Keep full evaluation execution local or in CI for the MVP.
- Use managed Postgres for durable evaluation history and future human labels;
  SQLite remains suitable for a reconstructable offline demo.

This design fits Render's ephemeral filesystem while keeping the recruiter demo functional after a restart.

## 11. Rollback Procedure

If deployment verification fails:

1. Do not continue sending public traffic to the broken release.
2. Save relevant Render logs without copying secrets into issues or chat.
3. Roll back to the most recent known-good Render deployment.
4. Reproduce the failure locally using production settings.
5. Add a regression test before applying the focused fix.
6. Redeploy and repeat every health and acceptance check.

Database migrations must be backward-compatible whenever a rollback may run older application code against a newer schema.

## 12. Debugging Guide

### Build fails while installing dependencies

Likely causes:

- dependency missing from `requirements.txt`;
- unsupported Python version;
- package requiring an unavailable system library; or
- stale lock/constraint metadata.

Inspect the first installation error in the Render build log, reproduce it in a clean local container, and fix the dependency declaration rather than manually modifying the running service.

### Render reports that no port is open

The process probably bound only to `127.0.0.1` or ignored Render's `PORT`. Gunicorn must bind to `0.0.0.0:$PORT`.

### `/health` works but `/health/ready` fails

The Python process is alive, but an essential dependency or seeded dataset is unavailable. Check initialization logs and the readiness failure category. Do not make readiness always return `200`; that would hide the real problem.

### Data disappears after a restart

Render's default filesystem is ephemeral. Confirm that public-demo data is recreated idempotently or move genuinely durable data to managed storage.

### First request is slow

The free service may have spun down after inactivity. Confirm Render service status, measure the cold-start duration, and decide whether optional external monitoring is worth the free-instance-hour usage.

### Deployment works locally but returns a server error

Check production-only differences: environment variables, case-sensitive filenames, migration state, debug assumptions, and missing static assets. Use a generic public error page while retaining structured, redacted server logs.

## 13. Release Checklist

### Application

- [ ] Project plan approved.
- [ ] Phase-specific implementation complete.
- [ ] Unit, integration, statistical, web, and deployment tests pass.
- [x] Production container smoke-tested (`Container smoke test` workflow).
- [x] Demo seed is deterministic and idempotent (`tests/test_demo.py`).
- [x] Public mode rejects all mutations and model calls (`tests/test_demo.py`).
- [ ] Accessibility and responsive-layout checks completed.

### Security and cost

- [ ] No `.env`, API key, local database, or sensitive output is tracked.
- [ ] `APP_ENV=production` and Flask debug mode is off.
- [ ] `DEMO_READ_ONLY=true`.
- [x] `LLM_PROVIDER=mock`. A production read-only process refuses to boot otherwise.
- [x] `MAX_RUN_COST_USD=0` for the public demo. A production read-only process refuses to boot otherwise.
- [ ] Secrets are configured only through Render's environment settings.

### Render

- [ ] Build and start commands verified.
- [ ] `/health` returns `200`.
- [ ] `/health/ready` returns `200` and is the configured health-check path.
- [ ] HTTPS homepage and static assets load.
- [ ] Seeded dashboard, comparison, and regression detail work.
- [ ] Logs are structured and redacted.
- [ ] Rollback path identified.

### Optional monitoring

- [ ] UptimeRobot points to the public `/health` endpoint.
- [ ] Five-minute check succeeds.
- [ ] Alert contact verified if enabled.
- [ ] Free-instance-hour usage accepted and documented.

## 14. Resume and Interview Value

Deployment adds evidence that EvalBench is more than a notebook or local prototype. It demonstrates:

- environment-based configuration and secret handling;
- safe separation between development and public-demo capabilities;
- containerized production execution;
- liveness versus readiness health design;
- external monitoring and honest uptime limitations;
- reproducible releases and rollback thinking; and
- cost-aware deployment of an AI application.

Interview explanation:

> I deployed the portfolio version in a read-only seeded mode. Recruiters can inspect real evaluation results without exposing a paid model endpoint. I separated liveness from readiness, made demo seeding idempotent for ephemeral hosting, and documented cold-start monitoring as a tradeoff rather than claiming the free tier provides production uptime.
