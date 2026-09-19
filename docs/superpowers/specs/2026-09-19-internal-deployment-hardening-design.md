# Internal Deployment Hardening Design

## Purpose

Prepare Annotation Desk for reliable use by approximately 20 internal users on one Linux server or VM. The application remains one Docker container containing the production React build and one FastAPI/Uvicorn process, with SQLite and all filesystem state below one persistent data root.

The service has no application-level authentication. Operators must expose it only through a company VPN, Tailscale, a private LAN, or equivalent firewall-restricted network.

## Existing Architecture

The existing repository already implements the intended core architecture:

- React and TypeScript are built by Vite and served by FastAPI from the same origin.
- API routes live below `/api/v1`; controlled media routes live below `/media`; other non-API routes use the SPA fallback.
- `ANNOTATE_TOOL_DATA_DIR` selects a root containing `app.sqlite3`, `catalogs/`, `projects/`, `staging/`, and `exports/`.
- SQLite connections enable WAL mode, foreign keys, and a 5-second busy timeout.
- Annotation decisions are row-level database updates performed in short transactions.
- Original label files are backed up and remain unchanged; exports apply database decisions in memory.
- Dataset and catalog imports validate ZIP paths, reject symlinks and duplicates, enforce archive limits, stage extraction, and publish only completed imports.
- A multi-stage Dockerfile builds and tests the frontend, installs pinned Python dependencies, and starts one Uvicorn process.
- Docker Compose supplies `/data`, a restart policy, and a health check.
- API errors use a structured response envelope, and unexpected exceptions are logged without returning tracebacks.

## Observed Gaps and Risks

### P0 — Required Before Deployment

1. **Startup storage validation is incomplete.** Startup creates directories and initializes SQLite, but it does not explicitly prove that each required data directory is writable before the application begins serving traffic. A read-only or incorrectly mounted volume can therefore fail only when a user performs an operation.
2. **Filesystem failures can reach client messages.** Import services currently convert some `OSError` messages directly into validation errors. Platform exception text may include absolute server paths.
3. **Deployment persistence is not operationally obvious.** Compose uses a named volume, while the required backup, restore, and server operations need a concrete host directory that administrators can inspect and protect.

### P1 — Strongly Recommended

1. **Operational logging is incomplete.** Unexpected errors are logged, but expected import failures and failed annotation writes lack focused event logs.
2. **Backup and restore are documentation-only.** Existing guidance recommends stopping the service, but there are no scripts that validate inputs, archive the whole state root, or prevent accidental restore over an active/nonempty target.
3. **Deployment documentation is incomplete.** Exact Linux commands for first deployment, health verification, backup, restore, upgrade, and container-replacement persistence testing are missing.
4. **Configuration discovery is incomplete.** There is no `.env.example` describing the supported production variables.
5. **Concurrency latency assertion is brittle.** The representative 20-client test produced no lock errors or lost updates, but its 300 ms p95 threshold failed at 327 ms in the baseline environment. Correctness and an appropriately generous upper bound should remain enforced while latency is reported as diagnostic evidence.

### P2 — Optional

1. Provide a repeatable Docker smoke-test procedure or helper that validates health and state persistence across container replacement when Docker is available.

## Selected Approach

Harden the existing implementation in place. Do not add authentication, a reverse proxy, a second process, PostgreSQL, distributed locks, task queues, or other infrastructure. Preserve the current data model, import pipeline, export behavior, and single-row annotation updates.

The alternatives considered were documentation-only changes, which leave real startup and information-disclosure risks, and a new production-mode configuration subsystem, which adds complexity without evidence that it is needed. Focused hardening is the smallest approach that satisfies the deployment requirements.

## Detailed Design

### Storage Configuration and Startup

`V2Paths` remains the authoritative layout for persistent state. Add a storage validation operation that:

1. Resolves the configured root.
2. Creates the root and required subdirectories when allowed.
3. Writes, flushes, and removes a small uniquely named probe in each writable directory relevant to runtime operations.
4. Initializes and probes SQLite after directory validation.
5. Raises a clear startup exception if validation fails.

The failure must be logged for operators without returning the configured absolute path through an API response. Development may continue to use the existing local default, while Docker explicitly sets `ANNOTATE_TOOL_DATA_DIR=/data`; startup must never replace an explicitly configured unusable path with another directory.

The health endpoint will reuse non-destructive database and storage probes and continue returning only status labels, never paths or environment contents.

### SQLite and Concurrency

Retain SQLite, WAL, foreign keys, the busy timeout, and one connection per repository operation. Annotation writes remain `BEGIN IMMEDIATE` transactions that update only the selected annotation and the owning project's timestamp.

The concurrency suite will verify:

- 20 clients can update different annotations without lock errors.
- The annotations include multiple boxes from the same source image.
- Every response succeeds and every unrelated update is present afterward.
- The final database passes an integrity check.
- Latency is measured and reported, with a generous failure ceiling intended to catch hangs rather than normal host variance.
- Exact-same-record behavior remains last-write-wins; no application lock is added.

### Import, Error, and Logging Safety

Keep all existing archive validation and atomic publish behavior. Expected import failures will produce stable, user-safe messages. Raw `OSError` text and absolute paths will be logged server-side as exceptions but replaced in client responses with a generic import/storage failure message.

Add focused logs for application startup, startup validation failures, rejected/failed imports, failed annotation writes, and unexpected API exceptions. Logs go to stdout/stderr through standard Python logging and avoid request bodies, uploaded contents, secrets, and unnecessary paths.

### Container and Compose Deployment

Retain the multi-stage Dockerfile, one Uvicorn process, `0.0.0.0`, configurable `PORT`, production React build, and Docker health check.

Change the Compose example to a bind-mounted host directory such as `./annotation-data:/data`. This makes persistence, permissions, backup, and restore explicit. Add only environment variables that the application supports, documented through `.env.example`.

The production deployment remains:

```text
internal users
    -> private network/VPN
    -> one Linux server or VM
    -> one Docker container
    -> FastAPI serving API, media, and React
    -> SQLite plus immutable project/catalog files under /data
```

### Backup and Restore

Use an offline whole-root backup for this single-process MVP:

1. Stop the Compose service.
2. Archive the entire host data directory, including SQLite sidecar files if present and every catalog/project file.
3. Restart the service and verify health.

The backup helper will refuse a missing data root and write a timestamped archive outside that root. The restore helper will require an explicit archive and target, reject unsafe/non-archive input, and refuse to overwrite a nonempty target unless the operator has first moved it aside. Documentation will require the application to remain stopped throughout restore. This produces a consistent SQLite/filesystem snapshot without adding online-backup coordination machinery.

### Documentation and Operations

Add deployment documentation with exact Linux commands for:

- Development setup and tests
- Production build
- Docker build and run
- Docker Compose deployment with a host bind mount
- Data-directory ownership and permissions
- Health checking
- Offline backup and restore
- Updating to a new application version without deleting persistent state
- Container replacement and persistence smoke testing

The documentation will prominently state that persistent storage is mandatory and that the service must not be exposed directly to the public internet.

## Testing Strategy

Use test-driven changes for each behavior. Verification will include:

- Backend startup, health, database configuration, storage validation, imports, exports, media confinement, annotation updates, persistence, and concurrency tests.
- Frontend unit tests, type checking, and production build.
- Existing Playwright critical path when its browser/runtime is available.
- Docker image build and a mounted-directory container replacement test when Docker is available.
- Backup and restore round trip using a temporary data root.

Any environment-dependent check that cannot run will be reported as `NOT VERIFIED` with the exact production-server command required.

## Acceptance Criteria

The work is complete when the repository demonstrates the original prompt's 18 acceptance criteria without changing the intentionally simple architecture. In particular, replacing the container must preserve all state, startup must reject unusable storage, concurrent writes must retain all unrelated decisions without lock failures, and deployment/backup procedures must be reproducible by an operator from the documentation alone.
