# Internal Production Deployment

This runbook deploys Annotation Desk for approximately 20 users on one Linux server or VM. The server runs one Docker container, one Uvicorn process, one SQLite database, and one persistent host directory.

> **Never deploy without persistent storage.** The `./annotation-data` host directory must remain mounted at `/data` whenever the container runs.

> **The application must not be exposed directly to the public internet.** It intentionally has no accounts, passwords, or authorization. Permit access only through Tailscale, a company VPN, a private LAN, or firewall rules restricted to the company network.

## Prerequisites

- A Linux server with current Docker Engine and the Docker Compose plugin.
- Git and `curl`.
- Access controls at the VPN, firewall, or private-network layer.
- Enough disk space for uploaded datasets plus external backups.

Keep the checkout, live data, and backups on durable storage. The examples use:

```text
/opt/annotation-desk/annotation-data   live application state
/opt/annotation-desk/backups          offline backup archives
```

Do not use `chmod 777`. Create the directories as the account that operates Docker and ensure the Docker daemon can read and write `annotation-data`:

```bash
sudo mkdir -p /opt/annotation-desk
sudo chown "$USER":"$USER" /opt/annotation-desk
cd /opt/annotation-desk
```

## First deployment

```bash
git clone https://github.com/yodsakitfirst/annotate_tool.git annotation-desk
cd annotation-desk
mkdir -p annotation-data backups
cp .env.example .env
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health
```

A healthy response is:

```json
{"status":"ok","database":"available","storage":"writable"}
```

The Compose service binds host port `8000`. Restrict that port before inviting users. To inspect startup or storage failures:

```bash
docker compose logs --tail=200 app
docker compose logs -f app
```

## Production image and direct Docker run

Compose is the recommended operator interface. To build the same image directly:

```bash
docker build -t annotation-desk:local .
```

To run it with the same durable host directory:

```bash
mkdir -p annotation-data
docker run -d \
  --name annotation-desk \
  --restart unless-stopped \
  -p 8000:8000 \
  -e PORT=8000 \
  -e ANNOTATE_TOOL_DATA_DIR=/data \
  -v "$(pwd)/annotation-data:/data" \
  annotation-desk:local
curl --fail http://127.0.0.1:8000/api/v1/health
```

Do not run a development Vite server or mount source code in production. FastAPI serves the compiled React application, API, and controlled media from the one container.

## Persistent state

Back up and preserve the entire `./annotation-data` directory. It contains:

```text
annotation-data/
├── app.sqlite3
├── catalogs/
├── projects/
├── staging/
└── exports/
```

SQLite may also create `app.sqlite3-wal` and `app.sqlite3-shm` while the service is running. Never copy individual files from the live directory independently. Catalog files, project datasets, original labels, decisions, and metadata form one application state.

The container is disposable. `docker compose down`, rebuilding the image, and replacing the container do not remove `./annotation-data`.

## Offline backup

The included backup helper creates an atomic compressed archive of the whole data root. Stop the service first so SQLite and filesystem state are consistent:

```bash
cd /opt/annotation-desk/annotation-desk
docker compose down
./scripts/backup.sh ./annotation-data ./backups
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
```

Copy the resulting `backups/annotation-desk-YYYYMMDDTHHMMSSZ.tar.gz` to storage outside this server. The helper refuses to place backups inside the live data root.

## Restore

Restoration requires downtime. The helper refuses to overwrite a nonempty target and rejects archive traversal paths.

```bash
cd /opt/annotation-desk/annotation-desk
docker compose down
mv annotation-data "annotation-data.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
./scripts/restore.sh ./backups/annotation-desk-YYYYMMDDTHHMMSSZ.tar.gz ./annotation-data
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
```

Replace `annotation-desk-YYYYMMDDTHHMMSSZ.tar.gz` with the exact archive filename. After verifying projects, catalogs, annotation decisions, and export, move the `annotation-data.before-restore-*` directory to protected storage or delete it through the normal operator retention process.

## Deploying an update

Create a consistent backup before changing the checkout or image:

```bash
cd /opt/annotation-desk/annotation-desk
docker compose down
./scripts/backup.sh ./annotation-data ./backups
git pull --ff-only
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
docker compose logs --tail=100 app
```

The update does not delete or replace `./annotation-data`. If the new version fails its health check, stop it, check out the previously deployed Git revision, rebuild, start it with the same data directory, and verify health. Restore the pre-update backup only when the data itself must be rolled back.

## Container-replacement persistence smoke test

Perform this before the first production launch and after changing storage configuration:

1. Start the service and verify health:

   ```bash
   docker compose up -d --build
   curl --fail http://127.0.0.1:8000/api/v1/health
   ```

2. In the UI, upload `sample_data/sample_reference_catalog.zip`, create a project from `sample_data/sample_dataset.zip`, change one annotation, and download an export. Record the project name and selected class.
3. Replace the container without deleting the host data directory:

   ```bash
   docker compose down
   test -f ./annotation-data/app.sqlite3
   docker compose up -d
   curl --fail http://127.0.0.1:8000/api/v1/health
   ```

4. Reopen the same project. Confirm the catalog, project, annotation decision, progress, and export are unchanged.
5. Finish with an offline backup/restore rehearsal into a separate empty directory:

   ```bash
   docker compose down
   archive=$(./scripts/backup.sh ./annotation-data ./backups)
   ./scripts/restore.sh "$archive" ./restore-rehearsal
   test -f ./restore-rehearsal/app.sqlite3
   rm -rf ./restore-rehearsal
   docker compose up -d
   ```

The final `rm -rf` target is the explicitly named rehearsal directory created by the immediately preceding command. Do not substitute the live `annotation-data` path.

## Development and release verification

Windows development commands are in the repository README. The corresponding Linux verification commands are:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q annotate_tool scripts tests app.py
npm --prefix frontend ci
npm --prefix frontend test -- --run --no-file-parallelism --maxWorkers=1
npm --prefix frontend run typecheck
npm --prefix frontend run build
(cd frontend && npx playwright install chromium && npm run test:e2e)
docker compose build
```

Do not deploy a revision whose backend tests, frontend tests, production build, or Docker build fail.
