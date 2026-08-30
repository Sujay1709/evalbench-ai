# EvalBench Deployment Guide

> **Status: approved on August 15, 2026; not yet deployed.** Commands marked **Future command** describe the intended deployment contract and must be verified against the implemented application before use.

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

## 3. Expected Deployment Files

These files will be created during the approved implementation phases:

| File | Responsibility |
|---|---|
| `pyproject.toml` | Python version, runtime dependencies, and developer tools. |
| `.env.example` | Documented environment-variable names with no secrets. |
| `Dockerfile` | Reproducible production image. |
| `.dockerignore` | Excludes local databases, caches, secrets, and development artifacts. |
| `render.yaml` | Render Blueprint containing build, start, health-check, and environment settings. |
| `compose.yaml` | Optional local multi-service environment. |
| `app/__init__.py` | Flask application factory. |
| `evalbench/bootstrap_demo.py` | Idempotent migration and demo-data initialization. |
| `tests/deployment/` | Container and health-endpoint smoke tests. |

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

## 5. Local Pre-deployment Checks

Run these checks only after their files and commands have been implemented.

### Native Python workflow

**Future commands:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
pytest
python -m evalbench.cli demo seed
flask --app 'app:create_app()' run --debug
```

### Container workflow

**Future commands:**

```bash
docker build -t evalbench:local .
docker run --rm -p 8000:8000 --env-file .env evalbench:local
```

### Required smoke checks

In another terminal:

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/health/ready
```

Expected liveness response:

```json
{"status":"ok"}
```

Before deployment, also verify:

- the complete test suite passes;
- the production container starts without development dependencies;
- seeded demo data loads more than once without duplication;
- public demo mode blocks every write and evaluation-run action;
- the site does not display secrets, hidden holdout labels, stack traces, or local paths;
- static assets load correctly behind HTTPS; and
- the dashboard works on desktop and mobile widths.

## 6. Production Process Contract

The web service will run Flask behind Gunicorn. The exact module path will be confirmed during implementation.

**Proposed future start command:**

```bash
python -m evalbench.bootstrap_demo && gunicorn 'app:create_app()' --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120
```

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

### Step 2: Validate `render.yaml`

The future Blueprint should express approximately this contract:

```yaml
services:
  - type: web
    name: evalbench
    runtime: python
    plan: free
    buildCommand: pip install .
    startCommand: python -m evalbench.bootstrap_demo && gunicorn 'app:create_app()' --bind 0.0.0.0:$PORT
    healthCheckPath: /health/ready
    envVars:
      - key: APP_ENV
        value: production
      - key: DEMO_READ_ONLY
        value: "true"
      - key: LLM_PROVIDER
        value: replay
      - key: MAX_RUN_COST_USD
        value: "0"
      - key: SECRET_KEY
        generateValue: true
```

This is a design preview, not a file to deploy yet. Its syntax and commands must be tested after the application exists.

### Step 3: Create the Render service

1. Sign in to Render and create a new Blueprint or Web Service from the GitHub repository.
2. Confirm the free instance choice is appropriate for a portfolio demonstration.
3. Review every environment variable before the first deployment.
4. Do not add an LLM API key to the public demo.
5. Confirm `/health/ready` is configured as the Render health-check path.
6. Deploy the selected commit.

### Step 4: Verify the release

Replace `<service-name>` with the actual Render service name:

```bash
curl --fail https://<service-name>.onrender.com/health
curl --fail https://<service-name>.onrender.com/health/ready
```

Then manually verify:

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

The first public demo should favor reliability and cost control over hosted write capability.

- Seed precomputed, non-sensitive results during startup.
- Make seed operations idempotent so restarts do not duplicate records.
- Treat the public demo database as reconstructable.
- Do not use the container filesystem for irreplaceable user data.
- Keep full evaluation execution local or in CI for the MVP.
- Move to managed Postgres only when durable hosted writes are a real requirement.

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

- dependency missing from `pyproject.toml`;
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
- [ ] Production container smoke-tested.
- [ ] Demo seed is deterministic and idempotent.
- [ ] Public mode rejects all mutations and model calls.
- [ ] Accessibility and responsive-layout checks completed.

### Security and cost

- [ ] No `.env`, API key, local database, or sensitive output is tracked.
- [ ] `APP_ENV=production` and Flask debug mode is off.
- [ ] `DEMO_READ_ONLY=true`.
- [ ] `LLM_PROVIDER=replay` or `mock`.
- [ ] `MAX_RUN_COST_USD=0` for the public demo.
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

> I deployed the portfolio version in a read-only replay mode. Recruiters can inspect real evaluation results without exposing a paid model endpoint. I separated liveness from readiness, made demo seeding idempotent for ephemeral hosting, and documented cold-start monitoring as a tradeoff rather than claiming the free tier provides production uptime.
