# Supabase database integration

## Scope and status

This is a PostgreSQL connection integration, not a hosted deployment. Flask,
SQLAlchemy, and Alembic remain the application stack. No Supabase SDK, Auth,
Storage, Realtime, vector search, or browser database client is required.
SQLite remains the default for offline development and tests. Local PostgreSQL
tests exercise the same psycopg driver and migrations used for Supabase; they do
not prove that a particular hosted project is reachable or correctly permissioned.
No hosted migration or paid model call is part of automated testing.

Persistent PostgreSQL keeps runs and cached responses independent of Render's
ephemeral disk. Phase 5 can then store judge evidence and human labels in the same
transactional database, without introducing a second persistence system.

## 1. Choose the endpoint

Create a Supabase project yourself and obtain its URL from **Connect**. Use a
direct connection when the backend has IPv6 connectivity, or the **Session
pooler** on port 5432 when it needs IPv4. Copy the exact pooler hostname and role
username from the dashboard; do not construct them from a region name.

Transaction pooling on port 6543 is intentionally outside this slice. Migrations
and our session timezone configuration require the direct/session connection
contract. Do not change ports or disable security to work around a connection error.

Source: [Supabase connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
and [SQLAlchemy integration guide](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT).

## 2. Configure verified TLS and bounded pooling

Install `requirements-dev.txt` locally or `requirements.txt` on the backend.
Set the following in an ignored `.env` or the hosting platform's secret settings:

```dotenv
DATABASE_URL=postgresql+psycopg://evalbench_runtime:PERCENT_ENCODED_PASSWORD@COPIED_HOST:5432/postgres
DATABASE_SSL_ROOT_CERT=/absolute/path/to/downloaded-supabase-ca.crt
DATABASE_POOL_SIZE=3
DATABASE_MAX_OVERFLOW=2
DATABASE_POOL_TIMEOUT_SECONDS=30
DATABASE_POOL_RECYCLE_SECONDS=300
DATABASE_CONNECT_TIMEOUT_SECONDS=10
```

Download the database CA certificate through Supabase's SSL configuration and
make it readable by the backend process. Mount it in the deployment filesystem
and point to that deployment path, not your Mac's path. A CA certificate is not a
private key, but private keys and database passwords must never enter git.

`postgres://` and `postgresql://` URLs are normalized to `postgresql+psycopg://`.
Percent-encode reserved characters in passwords. URL query options are restricted
to `sslmode` and `sslrootcert`; timeouts and pooling use the variables above.
Hosted connections default to `verify-full`, which verifies both the certificate
chain and hostname. Weaker modes are rejected, not silently upgraded or retried.
Only loopback development/testing may use plaintext; production may not.

Each process can open at most `DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW`
connections. Budget across Gunicorn workers **and** workflow processes; two
workers at the defaults can consume ten connections, before migration or other
clients. `pool_pre_ping` checks reused connections; it does not replay failed
transactions or guarantee availability. Sessions use UTC for consistent timestamps.

Never log Flask's entire config, connection arguments, or environment. Settings
mask the database URL and validation errors omit input values; SQLAlchemy hides
statement parameters. These safeguards are not a general-purpose log scrubber.

## 3. Separate migration and runtime permissions

Use a trusted administrative session to provision roles. Use a schema-owner role
for migrations, and a non-owner `evalbench_runtime` role without `BYPASSRLS`,
superuser, or role-creation privileges for evaluation execution. Run migrations
with the migration role's URL supplied privately as `DATABASE_URL`:

```bash
flask --app evalbench:create_app db upgrade
flask --app evalbench:create_app db check
```

Then switch the backend secret to the runtime URL. Do not leave administrative
credentials in the web process. PostgreSQL CLI runs and queued runs require the
current Alembic revision; unlike SQLite they never call `create_all()`.

For the existing schema, the runtime grants are:

```sql
GRANT CONNECT ON DATABASE postgres TO evalbench_runtime;
GRANT USAGE ON SCHEMA public TO evalbench_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.evaluation_runs, public.example_results, public.response_cache
    TO evalbench_runtime;
GRANT SELECT ON TABLE public.alembic_version TO evalbench_runtime;
GRANT USAGE, SELECT ON SEQUENCE public.example_results_id_seq TO evalbench_runtime;
```

Review inherited/public privileges too: the runtime role must not own tables or
have schema CREATE privileges through another grant. UPDATE is needed for run
lifecycle finalization; application code still preserves completed run history.
No DELETE grant is required. Revisit grants explicitly when Phase 5 adds tables.
For a public read-only demo, use a separate SELECT-only role, `DEMO_READ_ONLY=true`,
`LLM_PROVIDER=mock`, no model keys, and no runtime/migration credentials.

The backend uses SQL connections, not Supabase's Data API. **Disable the Data API
for this backend-only project before exposing it publicly.** If other applications
need it enabled, first isolate EvalBench in an unexposed schema or design and test
RLS policies that deny browser roles while allowing the dedicated backend role.
Do not assume Flask's read-only mode protects a separately exposed Data API.
Never send a database URL or privileged Supabase key to the frontend.

Source: [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security).

## 4. Validate without a Supabase account

The normal suite remains offline:

```bash
pytest -ra
ruff check .
git diff --check
```

PostgreSQL-specific cases are explicitly skipped unless opted in. Use a disposable
local PostgreSQL 17 database named **evalbench_test** (never a real project database):

```bash
docker run --detach --name evalbench-postgres-test \
  --publish 127.0.0.1:55432:5432 \
  --env POSTGRES_USER=evalbench_test_admin \
  --env POSTGRES_PASSWORD=disposable-test-password \
  --env POSTGRES_DB=evalbench_test postgres:17
docker exec evalbench-postgres-test pg_isready -U evalbench_test_admin -d evalbench_test
EVALBENCH_TEST_POSTGRES_URL='postgresql+psycopg://evalbench_test_admin:disposable-test-password@127.0.0.1:55432/evalbench_test' pytest -ra
docker stop evalbench-postgres-test
```

Wait for `pg_isready` to report accepting connections before testing. The test
fixture refuses remote hosts, non-test database names, other drivers, and URL query
overrides. Each test owns a randomly named schema, which it drops afterward; it
never drops `public`. The dedicated GitHub Actions workflow uses the same local
service contract, without Supabase credentials or remote model/dataset calls.

Coverage includes fresh upgrade/downgrade/upgrade, existing-row metadata backfills,
required fields without defaults, schema drift, JSON/Boolean/timezone persistence,
repeated-run cache reuse, readiness, and PostgreSQL CLI migration enforcement.
TLS policy tests inspect driver configuration and rejection paths, not a live
Supabase TLS handshake.

## 5. Hosted smoke check and rollback

Only after roles, certificate, and Data API protection are configured, test against
a **new disposable Supabase project**, using the migration role first. Verify
`db upgrade` and `db check`, then use runtime credentials for an offline mock run:

```bash
python -m evalbench.cli run --split development
python -m evalbench.cli run --split development
```

Confirm two distinct runs, cached second responses, and persistence across a backend
restart. Verify the runtime role cannot create tables or delete rows, browser/Data
API access is denied, and `/health/ready` succeeds. No OpenAI key is needed.

Changing DATABASE_URL does **not** copy existing SQLite history. Retain a backup
and keep SQLite available; a reviewed data-transfer utility is separate work.
This PR changes no application schema or historical rows on its own. To roll back
the connection integration, stop writes, preserve the PostgreSQL data, and restore
the previous backend version/configuration. Do not downgrade a populated database
to `base`: round-trip migration tests are destructive only in their test schemas.

## Troubleshooting

- **CA file error:** use the deployment's readable certificate path; do not use `require` or `disable`.
- **Hostname verification failure:** use the exact Connect hostname and correct CA; do not replace it with an IP.
- **IPv6 unreachable:** choose Session pooler on 5432 and its matching role username.
- **Too many connections:** reduce per-process pool/overflow and account for all workers.
- **Migrations required:** run `db upgrade` with the migration role before starting runtime workloads.
- **Permission denied:** inspect the specific role/table/sequence grants; do not promote the runtime role to admin.
- **Tests skipped:** provide the local `EVALBENCH_TEST_POSTGRES_URL`; hosted URLs are deliberately rejected.
