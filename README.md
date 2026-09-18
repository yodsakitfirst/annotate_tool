# Annotation Desk

Annotation Desk is an internal YOLO class-review application. A React single-page interface and FastAPI API ship as one service. Teams can reuse reference catalogs across projects, click boxes directly, save one annotation at a time, and export corrected labels without changing uploaded originals.

There is deliberately no authentication or authorization. Every user can see and edit every project. Restrict network access at the deployment layer.

## Data formats

A dataset ZIP contains `images/`, optional matching `labels/`, and optional `classes.txt` or `data.yaml`, either at the archive root or inside one enclosing directory. Source class IDs may be any nonnegative integers; missing source names display as `Unknown source class <id>`.

A reusable reference catalog ZIP contains:

```text
catalog.yaml
references/
  0.jpg
  1.png
  7.webp
```

`catalog.yaml` must contain a nonempty numeric `names` mapping. IDs may be sparse. Every mapped ID needs exactly one readable numeric-named image, and no extra numeric reference image is allowed. JPG, JPEG, PNG, BMP, and WebP are supported.

## Local development

Python 3.12 and Node 22 are the tested versions.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location frontend
npm ci
npm run dev
```

In another terminal, from the repository root:

```powershell
$env:ANNOTATE_TOOL_DATA_DIR = (Resolve-Path .\workspace_v2)
.\.venv\Scripts\python.exe -m uvicorn annotate_tool.api.main:app --reload --host 127.0.0.1 --port 8000
```

Vite serves the development UI at `http://localhost:5173` and proxies `/api` and `/media` to FastAPI.

To run the combined production-style service locally:

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
$env:ANNOTATE_TOOL_DATA_DIR = (New-Item -ItemType Directory -Force .\workspace_v2).FullName
$env:PORT = "8000"
.\.venv\Scripts\python.exe -m uvicorn annotate_tool.api.main:app --host 0.0.0.0 --port $env:PORT
```

Open `http://localhost:8000`. The health endpoint is `GET /api/v1/health`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q annotate_tool scripts tests app.py
Set-Location frontend
npm test -- --run --no-file-parallelism --maxWorkers=1
npm run typecheck
npm run build
npx playwright install chromium
npx playwright test
```

The Python suite includes a 20-client concurrent-write test. The Playwright critical path uploads the sample catalog and dataset, clicks a box, relabels to a sparse target, navigates away and back, and downloads an export.

## Legacy reference-catalog migration

Only reusable reference catalogs are migrated. Legacy datasets, projects, owners, decisions, and progress are intentionally ignored and the source workspace remains untouched.

```powershell
.\.venv\Scripts\python.exe -m annotate_tool.migrations.import_legacy_catalogs `
  --legacy-root .\workspace `
  --target-root .\workspace_v2
```

The command fingerprints names and image contents, preserves sparse IDs, Unicode names, and image formats, and reports imported, skipped, and failed catalogs. Rerunning it is safe.

## Docker

Build and start the application in the background with Docker Compose:

```powershell
docker compose up --build -d
```

Open `http://localhost:8000`. Uploaded data and annotation decisions are stored in the named
`annotation-desk-data` volume. View logs or stop the application with:

```powershell
docker compose logs -f
docker compose down
```

Alternatively, build and run the single-service image directly:

```powershell
docker build -t annotation-desk .
docker volume create annotation-desk-data
docker run --rm -p 8000:8000 `
  -e PORT=8000 `
  -e ANNOTATE_TOOL_DATA_DIR=/data `
  -v annotation-desk-data:/data `
  annotation-desk
```

The multi-stage build runs frontend tests and produces fingerprinted assets before installing the pinned Python runtime dependencies. One Uvicorn process serves the API, controlled media, and SPA.

## Persistence and backup

`ANNOTATE_TOOL_DATA_DIR` is required for a durable deployment. Mount it on persistent storage. If it points into an ephemeral container filesystem, every uploaded catalog, project, and decision can disappear on redeploy or restart. The server logs a warning when the variable is absent; that warning does not make ephemeral storage safe.

Back up the entire data directory as one unit, including `app.sqlite3`, `catalogs/`, and `projects/`. For a simple single-process deployment, stop the container or use a filesystem snapshot before copying it:

```powershell
docker stop annotation-desk
Copy-Item -Recurse D:\annotation-desk-data D:\backups\annotation-desk-$(Get-Date -Format yyyyMMdd-HHmmss)
```

Uploaded label files and `backups/labels_original/` are immutable. Decisions live in SQLite. Exports are constructed in memory from the immutable originals and current decisions.

## Deployment limits

- Run exactly one application replica for this SQLite/filesystem MVP.
- Mount one writable persistent data directory and back it up externally.
- Restrict the service to the internal network because it has no login or permissions.
- Configure the platform request-size and request-timeout limits for synchronous ZIP imports.
- The hosting platform must pass `$PORT`, allow binding to `0.0.0.0`, preserve the mounted volume across restart/redeploy, and provide enough memory for ZIP validation.
- CloudViu compatibility is not claimed until its build command, port injection, persistent volumes, upload limits, request timeouts, memory limits, and sleep/restart behavior are verified.
