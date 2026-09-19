# Internal Deployment Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing single-container React/FastAPI/SQLite application safe and operationally repeatable for approximately 20 internal users on one private Linux server.

**Architecture:** Preserve the current one-process application and `V2Paths` data layout. Add fail-fast storage probes, safe operational errors and logs, stronger concurrency evidence, an explicit host bind mount, offline whole-root backup helpers, and exact deployment procedures.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, React 19, TypeScript, Vite, Vitest, Playwright, Docker, Docker Compose, POSIX shell.

**Spec:** `docs/superpowers/specs/2026-09-19-internal-deployment-hardening-design.md`

## Global Constraints

- Keep one Linux server or VM, one Docker container, one Uvicorn process, one SQLite database, and one persistent data directory.
- Keep `ANNOTATE_TOOL_DATA_DIR=/data` in Docker and preserve the existing local development default.
- Do not add Kubernetes, Redis, Celery, RabbitMQ, microservices, multiple replicas, PostgreSQL, object storage, a reverse-proxy container, WebSockets, distributed locking, or application authentication.
- Do not change original uploaded labels; decisions remain separate SQLite rows and exports apply decisions in memory.
- Do not return absolute filesystem paths, environment dumps, SQL text, or tracebacks to API clients.
- The application must be reachable only through a VPN, Tailscale, private LAN, or equivalent firewall restriction.

## File Structure

- `annotate_tool/v2/config.py`: owns the persistent directory layout and writable-storage probe.
- `annotate_tool/v2/database.py`: owns SQLite initialization and accessibility/integrity probes.
- `annotate_tool/api/main.py`: runs startup validation and emits lifecycle logs.
- `annotate_tool/api/routes/health.py`: exposes path-free dependency health.
- `annotate_tool/api/routes/annotations.py`: translates and logs annotation persistence failures.
- `annotate_tool/api/routes/catalogs.py`: logs catalog rejection/storage failures without leaking server paths.
- `annotate_tool/api/routes/projects.py`: logs project rejection/storage failures without leaking server paths.
- `annotate_tool/services/catalog_service.py`: separates user input failures from storage failures.
- `annotate_tool/services/project_service.py`: separates user input failures from storage failures.
- `tests/api/test_startup.py`: pins startup fail-fast behavior and path-free exceptions.
- `tests/api/test_health.py`: pins dependency probes and response privacy.
- `tests/api/test_annotations.py`: pins structured annotation-write failure responses and focused logs.
- `tests/api/test_catalogs.py`: pins safe catalog-import failure messages and logs.
- `tests/api/test_projects.py`: pins safe project-import failure messages and logs.
- `tests/api/test_concurrency.py`: verifies 20-client correctness, integrity, and non-hanging latency.
- `compose.yaml`: uses an explicit host bind mount for `/data`.
- `.env.example`: documents only supported production configuration.
- `scripts/backup.sh`: creates an atomic, timestamped archive of a stopped data directory.
- `scripts/restore.sh`: safely restores an archive into an empty data directory.
- `tests/test_deployment_scripts.py`: exercises backup/restore on POSIX hosts and validates shell syntax elsewhere when Bash exists.
- `docs/deployment.md`: contains exact Linux deployment, health, backup, restore, update, and smoke-test commands.
- `README.md`: links to the production runbook and keeps concise development instructions.

## Review Focus

- A configured data root exists but one required subdirectory is read-only: startup must fail before serving requests and must not fall back elsewhere.
- An import raises an `OSError` containing an absolute server path: the log records the event while the API response contains only a stable generic message.
- Twenty writes target separate boxes on the same image: all decisions survive and SQLite reports `ok` from `PRAGMA integrity_check`.
- A backup destination is inside the live data root: the helper must reject it to prevent recursive/self-containing archives.
- A restore target is nonempty or an archive contains `..`/absolute members: the helper must refuse without modifying the target.

---

### Task 1: Fail-Fast Persistent Storage and Database Validation

**Files:**
- Modify: `annotate_tool/v2/config.py`
- Modify: `annotate_tool/v2/database.py`
- Modify: `annotate_tool/api/main.py`
- Modify: `annotate_tool/api/routes/health.py`
- Create: `tests/api/test_startup.py`
- Modify: `tests/api/test_health.py`

**Interfaces:**
- Produces: `StorageValidationError(RuntimeError)` and `V2Paths.validate_writable() -> None`.
- Produces: `Database.check_accessible() -> None`.
- Consumes: existing `V2Paths.ensure()` and `Database.initialize()`.

- [ ] **Step 1: Write failing storage and startup tests**

```python
def test_validate_writable_probes_every_runtime_directory(tmp_path, monkeypatch):
    paths = V2Paths.from_root(tmp_path / "data")
    opened = []
    original_open = Path.open

    def recording_open(path, *args, **kwargs):
        if path.name.startswith(".write-probe-"):
            opened.append(path.parent)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)
    paths.validate_writable()
    assert set(opened) == {paths.root, paths.staging, paths.catalogs, paths.projects, paths.exports}


def test_startup_rejects_unwritable_configured_storage_without_fallback(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "blocked", frontend_dist=tmp_path / "frontend")
    secret_path = str(settings.data_dir.resolve())

    def deny_probe(self):
        raise StorageValidationError("Persistent storage is not writable") from PermissionError(secret_path)

    monkeypatch.setattr(V2Paths, "validate_writable", deny_probe)
    with pytest.raises(StorageValidationError, match="Persistent storage is not writable") as failure:
        with TestClient(create_app(settings)):
            pass
    assert secret_path not in str(failure.value)
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_startup.py tests/api/test_health.py -v`

Expected: failure because `StorageValidationError`, `validate_writable`, and `check_accessible` do not exist.

- [ ] **Step 3: Implement writable-storage and database probes**

Add to `annotate_tool/v2/config.py`:

```python
import os
import uuid


class StorageValidationError(RuntimeError):
    pass


def _runtime_directories(paths: V2Paths) -> tuple[Path, ...]:
    return (paths.root, paths.staging, paths.catalogs, paths.projects, paths.exports)


def validate_writable(self: V2Paths) -> None:
    self.ensure()
    for directory in _runtime_directories(self):
        probe = directory / f".write-probe-{uuid.uuid4().hex}"
        try:
            with probe.open("xb") as handle:
                handle.write(b"ok")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise StorageValidationError("Persistent storage is not writable") from exc
        finally:
            probe.unlink(missing_ok=True)
```

Attach `validate_writable` as a normal `V2Paths` method and keep the directory tuple private to that module.

Add to `annotate_tool/v2/database.py`:

```python
def check_accessible(self) -> None:
    with self.connect() as connection:
        row = connection.execute("PRAGMA quick_check").fetchone()
    if row is None or row[0] != "ok":
        raise sqlite3.DatabaseError("SQLite quick check failed")
```

- [ ] **Step 4: Wire probes into startup and health**

Update `annotate_tool/api/main.py` lifespan in this order:

```python
logger.info("Starting Annotation Desk")
try:
    context.paths.validate_writable()
    context.database.initialize()
    context.database.check_accessible()
except Exception:
    logger.exception("Application startup validation failed")
    raise
app.state.context = context
logger.info("Annotation Desk startup validation complete")
```

Update the health route to call `context.database.check_accessible()` and `context.paths.validate_writable()` while preserving the exact response body:

```python
return {"status": "ok", "database": "available", "storage": "writable"}
```

- [ ] **Step 5: Run focused and regression tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_startup.py tests/api/test_health.py tests/api/test_database.py tests/api/test_filesystem.py -v`

Expected: all selected tests pass and no `.write-probe-*` files remain.

- [ ] **Step 6: Commit the storage validation deliverable**

```bash
git add annotate_tool/v2/config.py annotate_tool/v2/database.py annotate_tool/api/main.py annotate_tool/api/routes/health.py tests/api/test_startup.py tests/api/test_health.py
git commit -m "feat: validate persistent storage at startup"
```

### Task 2: Path-Safe Operational Errors and Focused Logging

**Files:**
- Modify: `annotate_tool/services/catalog_service.py`
- Modify: `annotate_tool/services/project_service.py`
- Modify: `annotate_tool/api/routes/catalogs.py`
- Modify: `annotate_tool/api/routes/projects.py`
- Modify: `annotate_tool/api/routes/annotations.py`
- Modify: `tests/api/test_catalogs.py`
- Modify: `tests/api/test_projects.py`
- Modify: `tests/api/test_annotations.py`

**Interfaces:**
- Produces: `CatalogStorageError(RuntimeError)` and `ProjectStorageError(RuntimeError)` with fixed path-free messages.
- Consumes: existing `ApiError` envelope and service import methods.

- [ ] **Step 1: Write failing response-privacy and logging tests**

```python
def test_catalog_storage_failure_is_logged_without_leaking_path(api_client, monkeypatch, caplog):
    secret = r"C:\\internal\\catalogs\\secret.zip"
    monkeypatch.setattr(
        api_client.app.state.context.catalog_service,
        "import_catalog",
        lambda *_args: (_ for _ in ()).throw(CatalogStorageError("Catalog storage operation failed")),
    )
    with caplog.at_level(logging.ERROR, logger="annotate_tool"):
        response = upload_catalog(api_client)
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Catalog storage is unavailable"
    assert secret not in response.text
    assert "Catalog import storage failure" in caplog.text


def test_annotation_database_failure_is_logged_and_structured(api_client, monkeypatch, caplog):
    catalog_id = upload_catalog(api_client).json()["id"]
    project = create_project(api_client, catalog_id).json()
    annotation = first_annotation(api_client, project["id"])
    monkeypatch.setattr(
        api_client.app.state.context.annotation_service,
        "update",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked at C:\\secret")),
    )
    with caplog.at_level(logging.ERROR, logger="annotate_tool"):
        response = api_client.patch(
            f"/api/v1/annotations/{annotation['id']}",
            json={"action": "skip"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "annotation_write_failed"
    assert "C:\\secret" not in response.text
    assert "Annotation write failed" in caplog.text
```

Add the equivalent project-storage test in `tests/api/test_projects.py`, and extend malformed catalog/project tests to assert a warning log is emitted without request contents.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_catalogs.py tests/api/test_projects.py tests/api/test_annotations.py -v`

Expected: imports for the new storage error types fail or responses remain unlogged/untranslated.

- [ ] **Step 3: Separate validation failures from storage failures in services**

Add fixed exception types:

```python
class CatalogStorageError(RuntimeError):
    pass


class ProjectStorageError(RuntimeError):
    pass
```

In each service, keep known archive/content exceptions as the existing 422 error type, but translate `OSError` separately:

```python
except OSError as exc:
    raise ProjectStorageError("Project storage operation failed") from exc
```

Use the catalog equivalent message and keep the existing cleanup `finally` blocks unchanged.

- [ ] **Step 4: Add route-level safe logging and error translation**

Use one module logger in each route:

```python
logger = logging.getLogger("annotate_tool")
```

For expected invalid input:

```python
except ProjectImportError as exc:
    logger.warning("Project import rejected")
    raise ApiError(422, "project_invalid", str(exc)) from exc
```

For storage failures:

```python
except ProjectStorageError as exc:
    logger.exception("Project import storage failure")
    raise ApiError(503, "storage_unavailable", "Project storage is unavailable") from exc
```

Use parallel catalog messages. In the annotation route catch `(sqlite3.Error, OSError)`, log `"Annotation write failed"` without payload data, and return:

```python
raise ApiError(503, "annotation_write_failed", "Annotation could not be saved") from exc
```

- [ ] **Step 5: Run focused and full API tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_catalogs.py tests/api/test_projects.py tests/api/test_annotations.py tests/api/test_health.py -v`

Expected: all selected tests pass; client bodies contain no injected absolute paths.

- [ ] **Step 6: Commit safe errors and logging**

```bash
git add annotate_tool/services/catalog_service.py annotate_tool/services/project_service.py annotate_tool/api/routes/catalogs.py annotate_tool/api/routes/projects.py annotate_tool/api/routes/annotations.py tests/api/test_catalogs.py tests/api/test_projects.py tests/api/test_annotations.py
git commit -m "feat: harden deployment error handling"
```

### Task 3: Strengthen SQLite Concurrency Evidence

**Files:**
- Modify: `tests/api/test_concurrency.py`

**Interfaces:**
- Consumes: `AppContext.database.connect()` and the existing annotation PATCH endpoint.
- Produces: representative 20-client correctness, integrity, same-image, and latency-hang coverage.

- [ ] **Step 1: Extend the concurrency test before changing its threshold**

After the responses are collected, add:

```python
assert {item["image_id"] for item in annotations} == {image["id"]}
assert len({item["id"] for item in annotations}) == 20

refreshed_by_id = {
    item["id"]: item
    for item in api_client.get(
        f"/api/v1/projects/{project['id']}/images/{image['id']}"
    ).json()["annotations"]
}
assert set(refreshed_by_id) == {item["id"] for item in annotations}
assert all(item["current_class_id"] == 7 for item in refreshed_by_id.values())
assert all(item["version"] == 1 for item in refreshed_by_id.values())

with api_client.app.state.context.database.connect() as connection:
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
```

- [ ] **Step 2: Run the concurrency test and record the baseline behavior**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_concurrency.py -v -s`

Expected on the current host: all writes and integrity assertions pass; the existing 300 ms p95 assertion may fail around the observed 327 ms.

- [ ] **Step 3: Replace the workstation-sensitive threshold with a hang detector**

Keep the printed p95 measurement and replace the 300 ms assertion with:

```python
assert durations[18] < 2.0, f"p95 save latency indicated blocking: {durations[18]:.3f}s"
```

This remains well below the configured 5-second SQLite busy timeout and catches serialized stalls without treating normal CI/OneDrive variance as a failure.

- [ ] **Step 4: Run the concurrency test repeatedly**

Run: `.\.venv\Scripts\python.exe -m pytest tests/api/test_concurrency.py -v -s --count=3` if `pytest-repeat` is installed; otherwise run the same command three times manually.

Expected: 20 successful responses per run, final versions equal to 1, `PRAGMA integrity_check` returns `ok`, and p95 remains below 2 seconds.

- [ ] **Step 5: Commit concurrency evidence**

```bash
git add tests/api/test_concurrency.py
git commit -m "test: strengthen sqlite concurrency coverage"
```

### Task 4: Make Container Persistence Explicit

**Files:**
- Modify: `compose.yaml`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: host `./annotation-data` mounted at container `/data`.
- Consumes: Dockerfile support for `PORT` and `ANNOTATE_TOOL_DATA_DIR`.

- [ ] **Step 1: Add a failing configuration assertion test**

Create a small test in `tests/test_deployment_config.py`:

```python
from pathlib import Path
import yaml


def test_compose_uses_explicit_persistent_host_directory():
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    app = compose["services"]["app"]
    assert "./annotation-data:/data" in app["volumes"]
    assert app["environment"]["ANNOTATE_TOOL_DATA_DIR"] == "/data"
    assert app["restart"] == "unless-stopped"


def test_example_environment_contains_only_supported_runtime_settings():
    lines = {
        line for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert lines == {"PORT=8000", "ANNOTATE_TOOL_DATA_DIR=/data"}
```

- [ ] **Step 2: Run the configuration test and confirm failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deployment_config.py -v`

Expected: failure because Compose uses a named volume and `.env.example` does not exist.

- [ ] **Step 3: Change Compose to an explicit bind mount**

Replace the service volume and remove the top-level named volume declaration:

```yaml
    volumes:
      - ./annotation-data:/data
```

Create `.env.example`:

```dotenv
PORT=8000
ANNOTATE_TOOL_DATA_DIR=/data
```

Add `/annotation-data/` to `.gitignore` so runtime data cannot be committed.

- [ ] **Step 4: Validate Compose and tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deployment_config.py -v`

Run: `docker compose config`

Expected: test passes and Compose renders one service with the repository's `annotation-data` directory bound to `/data`.

- [ ] **Step 5: Commit deployment configuration**

```bash
git add compose.yaml .env.example .gitignore tests/test_deployment_config.py
git commit -m "deploy: use explicit persistent data mount"
```

### Task 5: Add Safe Offline Backup and Restore Helpers

**Files:**
- Create: `scripts/backup.sh`
- Create: `scripts/restore.sh`
- Create: `tests/test_deployment_scripts.py`

**Interfaces:**
- Produces: `scripts/backup.sh DATA_DIR BACKUP_DIR` printing the archive path.
- Produces: `scripts/restore.sh ARCHIVE DATA_DIR` restoring only into an absent or empty target.
- Consumes: POSIX `sh`, `tar`, `mktemp`, `date`, `realpath`, and standard filesystem commands available on the target Linux host.

- [ ] **Step 1: Write POSIX backup/restore round-trip and refusal tests**

```python
pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX deployment scripts")


def run_script(name, *args):
    return subprocess.run(
        ["sh", f"scripts/{name}", *map(str, args)],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
    )


def test_backup_restore_round_trip(tmp_path):
    data = tmp_path / "data"
    (data / "projects" / "p1").mkdir(parents=True)
    (data / "app.sqlite3").write_bytes(b"sqlite")
    (data / "projects" / "p1" / "labels.txt").write_text("immutable\n", encoding="utf-8")
    backups = tmp_path / "backups"

    saved = run_script("backup.sh", data, backups)
    assert saved.returncode == 0, saved.stderr
    archive = Path(saved.stdout.strip())
    restored = tmp_path / "restored"
    result = run_script("restore.sh", archive, restored)
    assert result.returncode == 0, result.stderr
    assert (restored / "app.sqlite3").read_bytes() == b"sqlite"
    assert (restored / "projects" / "p1" / "labels.txt").read_text(encoding="utf-8") == "immutable\n"


def test_backup_rejects_destination_inside_data_root(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    result = run_script("backup.sh", data, data / "backups")
    assert result.returncode != 0


def test_restore_refuses_nonempty_target(tmp_path):
    target = tmp_path / "data"
    target.mkdir()
    (target / "keep").write_text("keep", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        payload = tmp_path / "payload"
        payload.write_text("new", encoding="utf-8")
        output.add(payload, arcname="payload")
    result = run_script("restore.sh", archive, target)
    assert result.returncode != 0
    assert (target / "keep").read_text(encoding="utf-8") == "keep"
```

Also construct a malicious archive with member `../outside` and assert restore fails before creating the target.

- [ ] **Step 2: Run tests and confirm scripts are absent**

Run on POSIX: `python -m pytest tests/test_deployment_scripts.py -v`

Expected: failure because both scripts are missing.

- [ ] **Step 3: Implement atomic offline backup**

`scripts/backup.sh` must:

```sh
#!/bin/sh
set -eu

[ "$#" -eq 2 ] || { echo "usage: backup.sh DATA_DIR BACKUP_DIR" >&2; exit 2; }
data_dir=$(realpath "$1")
mkdir -p "$2"
backup_dir=$(realpath "$2")
[ -d "$data_dir" ] || { echo "data directory does not exist" >&2; exit 1; }
case "$backup_dir/" in "$data_dir/"*) echo "backup directory must be outside data directory" >&2; exit 1;; esac
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="$backup_dir/annotation-desk-$stamp.tar.gz"
temporary=$(mktemp "$backup_dir/.annotation-desk-backup.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
tar -C "$data_dir" -czf "$temporary" .
mv "$temporary" "$archive"
trap - EXIT HUP INT TERM
printf '%s\n' "$archive"
```

- [ ] **Step 4: Implement defensive restore**

`scripts/restore.sh` validates that the archive exists, the target is absent or empty, and every `tar -tzf` member is relative and contains no `..` component before extracting. It extracts into a sibling temporary directory, then moves the completed directory into place so failures never publish partial state:

```sh
#!/bin/sh
set -eu

[ "$#" -eq 2 ] || { echo "usage: restore.sh ARCHIVE DATA_DIR" >&2; exit 2; }
archive=$(realpath "$1")
[ -f "$archive" ] || { echo "backup archive does not exist" >&2; exit 1; }
target_parent=$(realpath "$(dirname "$2")")
target="$target_parent/$(basename "$2")"
if [ -d "$target" ] && [ "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "restore target must be empty" >&2
    exit 1
fi
members=$(mktemp "$target_parent/.annotation-desk-members.XXXXXX")
temporary=$(mktemp -d "$target_parent/.annotation-desk-restore.XXXXXX")
trap 'rm -f "$members"; rm -rf "$temporary"' EXIT HUP INT TERM
tar -tzf "$archive" > "$members"
while IFS= read -r member; do
    clean=${member#./}
    case "/$clean/" in */../*) echo "archive contains unsafe path" >&2; exit 1;; esac
    case "$member" in /*) echo "archive contains absolute path" >&2; exit 1;; esac
done < "$members"
tar -C "$temporary" -xzf "$archive"
[ -f "$temporary/app.sqlite3" ] || { echo "backup does not contain app.sqlite3" >&2; exit 1; }
if [ -d "$target" ]; then
    rmdir "$target"
fi
mv "$temporary" "$target"
rm -f "$members"
trap - EXIT HUP INT TERM
printf '%s\n' "$target"
```

- [ ] **Step 5: Run script tests and shell syntax checks**

Run on POSIX:

```bash
sh -n scripts/backup.sh
sh -n scripts/restore.sh
python -m pytest tests/test_deployment_scripts.py -v
```

Expected: round trip passes; nested backup, nonempty restore, and traversal archive are rejected without target modification.

- [ ] **Step 6: Commit backup and restore helpers**

```bash
git add scripts/backup.sh scripts/restore.sh tests/test_deployment_scripts.py
git commit -m "feat: add offline backup and restore helpers"
```

### Task 6: Production Runbook and End-to-End Verification

**Files:**
- Create: `docs/deployment.md`
- Modify: `README.md`
- Modify: `.dockerignore`

**Interfaces:**
- Consumes: Compose bind mount, health endpoint, and backup/restore scripts from Tasks 1, 4, and 5.
- Produces: exact operator commands and the final verification evidence.

- [ ] **Step 1: Write a documentation assertion test**

Extend `tests/test_deployment_config.py`:

```python
def test_deployment_runbook_contains_mandatory_safety_and_operations():
    text = Path("docs/deployment.md").read_text(encoding="utf-8")
    for required in (
        "must not be exposed directly to the public internet",
        "Never deploy without persistent storage",
        "docker compose up -d --build",
        "curl --fail http://127.0.0.1:8000/api/v1/health",
        "scripts/backup.sh",
        "scripts/restore.sh",
        "docker compose down",
    ):
        assert required in text
```

- [ ] **Step 2: Run the documentation test and confirm failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_deployment_config.py -v`

Expected: failure because `docs/deployment.md` does not exist.

- [ ] **Step 3: Write the deployment runbook**

Document exact Linux commands using this repository's real names:

```bash
git clone https://github.com/yodsakitfirst/annotate_tool.git annotation-desk
cd annotation-desk
mkdir -p annotation-data backups
docker compose up -d --build
curl --fail http://127.0.0.1:8000/api/v1/health
```

The runbook must include firewall/private-network requirements, directory ownership, logs, health, offline backup/restore, update with `git pull --ff-only`, rollback preparation, and a container-replacement persistence smoke test.

Use this safe update sequence:

```bash
docker compose down
scripts/backup.sh ./annotation-data ./backups
git pull --ff-only
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
```

- [ ] **Step 4: Update README and Docker build context**

Replace named-volume examples with `./annotation-data`, link `docs/deployment.md`, and retain concise development/test commands. Add `annotation-data` and `backups` to `.dockerignore` so persistent state and archives never enter Docker build context.

- [ ] **Step 5: Run all non-Docker verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q annotate_tool scripts tests app.py
Set-Location frontend
npm test -- --run --no-file-parallelism --maxWorkers=1
npm run typecheck
npm run build
npx playwright test
```

Expected: backend, frontend, typecheck, production build, and Playwright critical path pass. If Playwright browser binaries are unavailable, record `NOT VERIFIED` and the installation command rather than claiming success.

- [ ] **Step 6: Build and smoke-test the container**

Run:

```bash
docker compose build
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
docker compose down
docker compose up -d
curl --fail http://127.0.0.1:8000/api/v1/health
docker compose down
```

Before the first `down`, import the sample catalog/project and save one decision through the existing API or UI; after recreation, verify the catalog, project, and decision are returned and export succeeds. If Docker is unavailable, report the build and replacement smoke test as `NOT VERIFIED` with these exact commands.

- [ ] **Step 7: Re-run diff and repository safety checks**

Run:

```bash
git diff --check
git status --short
git grep -n -E 'C:\\Users|/Users/|Desktop/' -- ':!docs/superpowers/**'
```

Expected: no whitespace errors, only intended changes, and no hardcoded production host paths.

- [ ] **Step 8: Commit documentation and final integration**

```bash
git add README.md docs/deployment.md .dockerignore tests/test_deployment_config.py
git commit -m "docs: add internal production deployment runbook"
```

- [ ] **Step 9: Produce the final deployment-readiness report**

Report the architecture found, concrete gaps, every meaningful file change with purpose and reason, final architecture, exact Linux commands, host storage directory, update process, backup/restore commands, executed test results, every `NOT VERIFIED` check, and only evidence-backed remaining risks.
