# React + FastAPI Annotation Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit production UI with one FastAPI-served React application that imports reusable catalogs and YOLO datasets, persists per-box decisions, and exports losslessly corrected labels.

**Architecture:** Existing parsing, archive-safety, catalog-validation, and class-token replacement functions remain the domain core. A new SQLite repository owns v2 metadata and short decision transactions; services coordinate filesystem staging with database registration; thin FastAPI routes expose explicit schemas and confined media. A Vite/React SPA uses React Query for server state and local state for immediate box selection and optimistic class changes.

**Tech Stack:** Python 3.12, FastAPI, SQLite, Pillow, PyYAML, React 19, TypeScript, Vite, React Router, TanStack Query, Vitest, Testing Library, Playwright, Docker.

**Spec:** `docs/superpowers/specs/2026-09-18-react-fastapi-annotation-platform-design.md`

## Global Constraints

- Work in the current checkout and current branch; do not create a Git worktree.
- One FastAPI/Uvicorn process serves `/api/v1`, controlled `/media`, and the compiled SPA.
- Default data root is `./workspace_v2`; production durability requires `ANNOTATE_TOOL_DATA_DIR` on persistent storage.
- SQLite uses WAL, foreign keys, a busy timeout, and short transactions.
- No authentication, ownership, locks, queues, WebSockets, Redis, PostgreSQL, or speculative infrastructure.
- Source IDs are arbitrary nonnegative integers; target IDs must exist in the attached reusable catalog.
- Original label bytes remain immutable; exports replace only class tokens while preserving geometry, line order, and newline structure.
- Imports publish only after validation and registration; failures leave no visible or completed resource.

---

### Task 1: V2 Configuration, Schema, and Repositories

**Files:**
- Create: `annotate_tool/v2/config.py`, `annotate_tool/v2/database.py`, `annotate_tool/repositories/catalogs.py`, `annotate_tool/repositories/projects.py`, `annotate_tool/repositories/annotations.py`
- Create: `tests/api/test_database.py`
- Modify: `requirements.txt`, `requirements-dev.txt`

**Interfaces:**
- Produces: `V2Paths.from_root(root)`, `Database.initialize()`, catalog/project/image/annotation repository records and query/update methods.
- Persists the exact tables and indexes in the approved spec, plus an idempotent `legacy_catalog_migrations` fingerprint table.

- [ ] Write repository tests that initialize twice, verify WAL/foreign keys, insert sparse classes, query project summaries without filesystem access, and update one annotation with an incremented version.
- [ ] Run `python -m pytest tests/api/test_database.py -q` and confirm missing-module failures.
- [ ] Implement schema migrations and focused repositories with parameterized SQL and one connection per operation.
- [ ] Re-run the focused test and the existing Python suite.

### Task 2: Catalog Service, API Foundation, and Health

**Files:**
- Create: `annotate_tool/services/catalog_service.py`, `annotate_tool/api/main.py`, `annotate_tool/api/dependencies.py`, `annotate_tool/api/errors.py`, `annotate_tool/api/schemas/catalogs.py`, `annotate_tool/api/routes/catalogs.py`, `annotate_tool/api/routes/health.py`, `annotate_tool/api/routes/media.py`
- Create: `tests/api/conftest.py`, `tests/api/test_health.py`, `tests/api/test_catalogs.py`, `tests/api/test_media.py`

**Interfaces:**
- Produces: `create_app(settings=None)`, `CatalogService.import_catalog(name, zip_path)`, catalog list/detail/class pagination, and database-owned media tokens.
- Error responses are always `{"error":{"code":str,"message":str,"details":object}}`.

- [ ] Write tests for startup/health, empty lists, valid sparse upload, invalid rollback, pagination/search, media cache headers, and traversal/foreign-path rejection.
- [ ] Run focused tests and confirm route/service failures.
- [ ] Implement staged catalog import using existing `import_reference_catalog`, atomic same-root publish, transactional registration, structured exception translation, and confined file responses.
- [ ] Re-run focused tests and the legacy catalog tests.

### Task 3: Project Import, Indexing, and Image APIs

**Files:**
- Create: `annotate_tool/services/project_service.py`, `annotate_tool/api/schemas/projects.py`, `annotate_tool/api/schemas/images.py`, `annotate_tool/api/routes/projects.py`, `annotate_tool/api/routes/images.py`
- Create: `tests/api/test_projects.py`, `tests/api/test_images.py`

**Interfaces:**
- Produces: atomic `ProjectService.import_project(name, catalog_id, zip_path)`, project summaries/detail, paginated ordered images, and current-image payloads.
- Import persists image dimensions, ordered annotations, original lines/tokens, source display names, and problems exactly once.

- [ ] Write tests covering reusable catalogs, rollback/retry, sparse and unknown source IDs, ordering/geometry, missing/malformed labels, and list summaries.
- [ ] Run focused tests and confirm missing behavior.
- [ ] Implement staging, existing safe dataset extraction/loading, immutable backups, one database publication transaction, completion marker, and indexed read queries.
- [ ] Re-run focused tests plus importer/dataset tests.

### Task 4: Per-Annotation Decisions and Lossless Export

**Files:**
- Create: `annotate_tool/services/annotation_service.py`, `annotate_tool/services/export_service.py`, `annotate_tool/api/schemas/annotations.py`, `annotate_tool/api/routes/annotations.py`, `annotate_tool/api/routes/exports.py`
- Create: `tests/api/test_annotations.py`, `tests/api/test_exports.py`, `tests/api/test_concurrency.py`

**Interfaces:**
- Produces: `PATCH /api/v1/annotations/{id}` for `correct|relabel|skip`, versioned last-write-wins updates, and `GET /api/v1/projects/{id}/export`.
- Export reads backup/original labels and applies database decisions with `replace_class_token`; it never writes source labels.

- [ ] Write tests for all actions, invalid target IDs, unchanged prior state after failures, repeated last-write-wins, independent same-file decisions, exact byte/token preservation, and 20 concurrent writers.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement validation plus short update transactions and in-memory ZIP construction from originals.
- [ ] Re-run focused tests and storage/YOLO tests.

### Task 5: Legacy Catalog-Only Migration

**Files:**
- Create: `annotate_tool/migrations/import_legacy_catalogs.py`, `annotate_tool/migrations/__init__.py`
- Create: `tests/api/test_legacy_catalog_migration.py`

**Interfaces:**
- Produces: `python -m annotate_tool.migrations.import_legacy_catalogs --legacy-root PATH --target-root PATH` and a concise imported/skipped/failed summary.
- Stable fingerprints prevent duplicates; legacy datasets, owners, progress, and decisions are never copied.

- [ ] Write a legacy SQLite/filesystem fixture test for sparse IDs, Unicode names, copied images, untouched legacy data, and idempotent rerun.
- [ ] Run it and confirm migration is absent.
- [ ] Implement discovery from legacy `reference_classes`, validation/copy through current rules, fingerprints, and CLI exit behavior.
- [ ] Re-run migration and catalog tests.

### Task 6: React Shell, Routing, and Project/Catalog Screens

**Files:**
- Create: `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig*.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/styles.css`, `frontend/src/api/*`, `frontend/src/types/index.ts`, `frontend/src/components/AppShell.tsx`, `frontend/src/components/ProjectSidebar.tsx`, `frontend/src/components/ErrorBoundary.tsx`, `frontend/src/pages/NewProjectPage.tsx`, `frontend/src/pages/CatalogListPage.tsx`, `frontend/src/pages/NewCatalogPage.tsx`, `frontend/src/pages/CatalogDetailPage.tsx`, `frontend/src/test/*`

**Interfaces:**
- Produces: client-side routes from the spec, cached project/catalog APIs, collapsible searchable sidebar, and multipart creation screens.

- [ ] Add component tests for search/selection, client navigation, loading/empty/network states, upload success/errors, catalog pagination, and narrow-sidebar behavior.
- [ ] Run `npm test -- --run` and confirm component/module failures.
- [ ] Implement the responsive shell and screens with accessible labels, focus states, React Query, and the last-opened project local-storage redirect.
- [ ] Re-run tests and `npm run build`.

### Task 7: Annotation Workspace and Optimistic Interaction

**Files:**
- Create: `frontend/src/components/BoundingBoxOverlay.tsx`, `frontend/src/components/ImageNavigator.tsx`, `frontend/src/components/ObjectInspector.tsx`, `frontend/src/components/ReferenceClassBrowser.tsx`, `frontend/src/components/ErrorNotice.tsx`, `frontend/src/pages/AnnotationPage.tsx`
- Create: `frontend/src/test/annotation.test.tsx`, `frontend/src/test/bounding-box.test.tsx`

**Interfaces:**
- Box selection is entirely local; class selection updates the query cache optimistically and issues exactly one PATCH, with rollback/retry on error.

- [ ] Add tests for immediate/no-request box selection, SVG scaling/viewBox, selected/hover styling, object/image navigation, lazy paginated class results, Correct/Skip, optimistic success, rollback, and retry.
- [ ] Run focused Vitest tests and confirm missing behavior.
- [ ] Implement the workspace using SVG normalized coordinates, local selection state, query prefetch, mutation rollback contexts, and local-storage annotator attribution.
- [ ] Re-run frontend tests and production build.

### Task 8: SPA Serving, E2E, and Production Packaging

**Files:**
- Modify: `annotate_tool/api/main.py`, `README.md`, `requirements.txt`
- Create: `frontend/playwright.config.ts`, `frontend/e2e/critical-path.spec.ts`, `Dockerfile`, `.dockerignore`
- Remove from production: Streamlit entry/dependency after replacement verification (legacy domain modules remain).

**Interfaces:**
- FastAPI serves fingerprinted frontend assets with immutable caching and falls back to `index.html` for non-API routes only.
- Docker multi-stage build exposes `$PORT`, runs one Uvicorn process, and health-checks `/api/v1/health`.

- [ ] Add API SPA-fallback tests and a Playwright critical path using sample ZIPs.
- [ ] Verify they fail before static serving/production packaging.
- [ ] Implement SPA mounting/fallback, multi-stage image, `.dockerignore`, and operational documentation including durability/authentication warnings, backup, migration, local dev, combined run, and Docker commands.
- [ ] Run backend, frontend, E2E (when browser runtime is available), build, concurrency, and Docker verification; record any environment-limited check explicitly.

### Task 9: Final Acceptance Verification

**Files:** All files changed above.

- [ ] Run the complete Python suite and compile check.
- [ ] Run frontend unit tests, typecheck, and production build.
- [ ] Run the 20-client concurrency test and record timing/lock results.
- [ ] Run `git diff --check`, inspect `git diff --stat`, and re-read every acceptance criterion against implemented tests or direct evidence.
- [ ] Report architecture, commands, evidence, and only genuine external hosting limitations; do not claim unrun checks.
