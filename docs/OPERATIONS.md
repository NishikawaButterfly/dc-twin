# Operations

## Operating boundary

The shipped stack is a local reference deployment for synthetic scenarios. It has no end-user authentication, authorization, tenant isolation, rate limiting, or public TLS endpoint. Docker Compose publishes only the API on `127.0.0.1:8000`; PostgreSQL remains on the internal Compose network.

Do not bind the API to a public interface without an authenticated gateway, TLS, network policy, quotas, centralized secrets, audit logging, and a deployment-specific threat model.

## Configuration

| Variable | Purpose | Reference value |
|---|---|---|
| `DC_TWIN_DATABASE_URL` | SQLAlchemy PostgreSQL URL; when absent, use the bounded in-memory store | No application default |
| `DC_TWIN_POSTGRES_PASSWORD` | Compose-only database/application password interpolation | No production default; set explicitly |
| `DC_TWIN_HOST` | Uvicorn bind address used by the container/launch command | `127.0.0.1` for local execution |
| `DC_TWIN_PORT` | Uvicorn listen port | `8000` |
| `DC_TWIN_LOG_LEVEL` | Uvicorn/application log level | `INFO` |

Docker Compose reads a repository-root `.env` file for variable interpolation; the Python application does not load dotenv files. For Compose use only, copy `.env.example` to `.env`, set one consistent `DC_TWIN_POSTGRES_PASSWORD`, and keep `.env` untracked. Compose constructs `DC_TWIN_DATABASE_URL` for its services from that password.

For a direct host process, set the required variables explicitly in the shell or use CLI flags. Leave `DC_TWIN_DATABASE_URL` unset for in-memory mode; set it to a reachable PostgreSQL URL only when persistent storage is intended. Production credentials belong in a managed secret store, not Compose files, shell history, images, logs, or issue reports.

## Local in-memory operation

When `DC_TWIN_DATABASE_URL` is unset, the API uses a thread-safe in-memory adapter. This is useful for demonstrations and test runs:

```powershell
dc-twin serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. The in-memory adapter retains at most 100 content-addressed runs and evicts the oldest retained run first when a new distinct result exceeds that limit. All records disappear when the process exits.

## Container operation

Start the API, one-shot migration job, and internal database from the repository root:

```powershell
docker compose up --build
```

The `migrate` service runs this command after the database health check passes:

```powershell
alembic upgrade head
```

The `api` service starts only after that migration job completes successfully. Its container entry point is:

```powershell
python -m dc_twin.server
```

The entry point validates `DC_TWIN_HOST`, `DC_TWIN_PORT`, and `DC_TWIN_LOG_LEVEL`, then launches Uvicorn without the server-identification header. Compose supplies `0.0.0.0:8000` inside the container while publishing the port only on host loopback.

The application image runs as UID/GID `10001`, drops Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem, and receives only bounded temporary filesystems. PostgreSQL is not published on a host port.

Verify the boundary from the host:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/api/v1/reference-scenarios
```

Stop the services without deleting the database volume:

```powershell
docker compose down
```

Deleting a Compose volume is destructive and outside the normal stop procedure. Confirm the exact project and backup status before any volume-removal command.

## Health semantics

`/health/live` reports whether the API process can serve requests. It intentionally does not query PostgreSQL. Use it for process restart decisions.

`/health/ready` verifies the configured run store. It returns `503` when PostgreSQL cannot answer a minimal query. Use it to remove an instance from traffic, not as an automatic instruction to delete or rebuild data.

## Migration policy

Apply `alembic upgrade head` before a new application version begins serving. Back up the database and review the migration before production rollout. Version 0.1.0 does not promise automated downgrade safety; rollback should restore a tested backup and the matching application image rather than assuming a reverse migration is lossless.

The API does not create schema objects opportunistically during requests. A persistent deployment that has not applied migrations should remain not ready.

## Persistence and retention

The PostgreSQL adapter stores content-addressed snapshot, scenario, and simulation-result rows. Existing result content is not updated by a repeated identical run. Version 0.1.0 performs no automatic deletion from PostgreSQL.

An operator must define retention according to the deployment's purpose, data classification, legal obligations, backup policy, and storage budget. A future deletion workflow must account for snapshot/scenario references, simulation rows, backups, replicas, and audit evidence. Do not manually delete individual rows without a reviewed referential-integrity and recovery plan.

The public reference fixtures are synthetic, but a private deployment may still treat topology and scenario records as sensitive architectural information.

## Backup and recovery

For PostgreSQL deployments:

1. Establish encrypted, access-controlled logical or physical backups on a documented schedule.
2. Record the application image, engine version, migration revision, and backup timestamp together.
3. Test restoration into an isolated environment.
4. After restore, verify readiness, retrieve a known run, and execute replay against its computation hash.
5. Keep recovery credentials separate from application credentials.

A computation hash can reveal post-restore drift; it does not replace a database backup or authenticate the backup's origin.

## Observability

Every HTTP response includes `X-Request-ID`. Supply a bounded `X-Request-ID` from the gateway to correlate access logs; the API creates a UUID when the header is absent or invalid.

Monitor at least:

- liveness and readiness status;
- request rate, latency, and status by route;
- `413`, `422`, `409`, and `5xx` rates;
- PostgreSQL connection and storage health;
- container restarts and memory/CPU saturation;
- run volume and retained database size; and
- replay mismatches.

Do not log complete snapshots, scenarios, results, database URLs, authorization headers, or exception tracebacks to an untrusted sink. Use structured fields for request ID, error code, route template, engine version, and duration.

## Incident runbooks

### Readiness returns 503

1. Confirm liveness first.
2. Check PostgreSQL service health and network reachability without printing credentials.
3. Confirm the configured database exists and the application role can connect.
4. Check that migrations reached `head`.
5. Restore traffic only after readiness is stable and a known run can be retrieved.

Do not erase or recreate the database merely because readiness failed.

### A run returns 404

Validate the run-ID syntax and deployment instance. In memory mode, the record may have been evicted or lost on restart. In PostgreSQL mode, check the correct environment and retention history. Treat a run ID as a locator, not proof that the record must exist forever.

### Replay reports a mismatch

Remove the instance from release promotion, preserve the original result and logs, record engine/package/image versions, and reproduce against the same canonical inputs. Compare contract version, event ordering, integer calculations, dependency changes, and serialization behavior. Do not overwrite the historical result or dismiss the mismatch as rounding.

### Resource-limit errors increase

Determine whether callers are accidentally using the wrong endpoint or intentionally exhausting resources. Preserve bounded failures, add gateway rate limits or quotas, and scale only after understanding the workload. Do not raise structural limits without performance and abuse testing.

## Upgrade checklist

1. Read `CHANGELOG.md` and all new ADRs.
2. Back up PostgreSQL and record the current image and migration revision.
3. Build and scan the candidate image from a reviewed commit.
4. Apply migrations in a non-production environment.
5. Run the reference scenarios and compare exact acceptance metrics.
6. Replay retained representative runs where the contract promises compatibility.
7. Verify API, CSV export, UI, liveness, readiness, and security headers.
8. Deploy with a rollback window and monitor error and replay signals.

## Shutdown

Stop accepting new traffic, allow active synchronous requests to finish within the platform timeout, and terminate the API normally. PostgreSQL must complete its own orderly shutdown or remain managed by the database platform. The in-memory adapter has no durable shutdown snapshot by design.
