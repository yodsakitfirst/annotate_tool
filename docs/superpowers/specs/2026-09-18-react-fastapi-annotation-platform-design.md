# React + FastAPI Annotation Platform Migration

## Implementation handoff prompt

You are working in the existing repository at `C:\Users\First\OneDrive\Desktop\annotate_tool`. Replace the Streamlit user interface with a responsive React frontend and expose the existing Python annotation capabilities through FastAPI. Work in the current checkout; do not create a separate application repository or a Git worktree.

This is an internal-team MVP. Optimize for a smooth annotation workflow and a simple, portable deployment. Do not add authentication, passwords, roles, project ownership, Redis, Celery, WebSockets, Kubernetes, microservices, or other speculative infrastructure.

Before changing code, inspect the repository, its tests, and the existing design documents. Preserve and reuse working Python domain behavior where appropriate, especially safe ZIP inspection/import, YOLO parsing, class-token replacement, reference-catalog validation, bounding-box calculations, backups, and export behavior. Use test-driven development for changes and keep commits focused.

## Product goal

Build a fast internal annotation web application in which more than 20 team members may browse all projects and annotate any project. Interactions must feel immediate: clicking a bounding box, moving between objects, searching classes, and selecting a class must not reload or reconstruct the entire page.

The application will initially be deployed as one container on a free cloud plan. The exact hosting platform capabilities are not yet confirmed, so deployment must be portable and must clearly require a persistent mounted data directory. React and FastAPI must ship as one deployable service.

## Decisions already approved

- Replace Streamlit with React + FastAPI.
- Build one React single-page application and one FastAPI service.
- In production, FastAPI serves the compiled React files and the JSON API from the same origin.
- Keep SQLite for this MVP, configured for WAL mode, a busy timeout, foreign keys, and short transactions.
- Store uploaded datasets and reference images on a persistent server filesystem.
- Do not implement accounts, passwords, login, permissions, or project ownership.
- Every user can see and open every project.
- Multiple users may edit the same project and image concurrently.
- Do not implement locking. Updates are last-write-wins at the individual bounding-box level.
- Preserve an optional annotator display name in browser local storage only for audit attribution; it is not authentication and may be blank.
- Preserve only the existing reference catalog during migration. Do not migrate existing datasets, annotation decisions, progress, or ownership records into the new application.
- Make reference catalogs reusable. A saved catalog is uploaded once and can be attached to multiple projects.
- Source datasets may contain any number of nonnegative source class IDs, including sparse or unknown IDs.
- A saved annotation may target only a class ID present in the project's selected reference catalog.
- The original YOLO geometry tokens, box order, and line structure must remain lossless. Export changes only the class token of relabeled annotations.
- Keep the implementation intentionally simple and leave clean storage/repository boundaries for a later PostgreSQL or object-storage migration.

## User experience

### Application shell

Use a desktop-first responsive layout similar in interaction model to common annotation tools, without copying their branding.

The permanent left sidebar contains:

- Application name.
- Search field for projects.
- A scrollable list of every project.
- Each project row shows a thumbnail, project name, image count, and reviewed/total progress.
- The active project is visually distinct.
- A `New project` action.
- A `Reference catalogs` management action.
- Sidebar collapse/expand behavior for narrow screens.

Switching projects updates the workspace through client-side routing/state. It must not reload the browser page.

### Annotation workspace

The main workspace contains:

- Current project name and concise progress.
- Previous/next image controls and an image-position indicator.
- Previous/next object controls and an object-position indicator.
- The original image with an SVG bounding-box overlay.
- Every valid annotation is directly clickable.
- Boxes show compact numeric object labels and clear selected/hover states.
- Clicking a box updates the selection immediately in React without waiting for an API request.
- The selected object's crop, source class ID/name, current target class, and review status.
- `Correct` and `Skip` actions.
- A searchable, virtualized or paginated reference-class panel with lazy-loaded thumbnails.
- Clicking a reference class optimistically updates the selected object and sends one small save request.
- On save failure, roll back the optimistic update and show a concise retryable error.
- Do not render all full-sized reference images at once.
- Preserve keyboard-friendly previous/next navigation and clear focus styles.

On smaller screens, the project sidebar may collapse and the class panel may stack below the image. The bounding-box overlay must scale with the displayed image while retaining correct hit testing.

### Project creation

`New project` opens a focused form that accepts:

- Project name.
- Dataset ZIP.
- One previously saved reference catalog.

The dataset ZIP follows the existing accepted YOLO layout: `images/`, optional `labels/`, and optional `classes.txt` or `data.yaml`, either at the archive root or within the already-supported enclosing-directory shape. Reuse the existing archive safety limits and validation. Import can be a synchronous operation for the MVP; show clear upload/import progress states in the frontend and do not introduce a background queue.

After a successful import, open the new project. On failure, remove incomplete staged data and return a structured error. An import retry must not expose a half-created project.

### Reference catalog library

Provide a catalog management screen with:

- Catalog name.
- Class count.
- A small thumbnail preview.
- Creation date.
- Upload-new-catalog action.
- Read-only catalog detail showing class ID, class name, and reference image.

The uploaded reference catalog ZIP format remains:

```text
catalog.yaml
references/
  0.jpg
  1.png
  7.webp
```

`catalog.yaml` contains a nonempty numeric `names` mapping. IDs are nonnegative and may be sparse. Names are nonblank. Every mapping ID has exactly one readable numeric-named image, and no image may exist without a mapped name. Continue supporting JPG, JPEG, PNG, BMP, and WebP.

Catalog deletion is out of scope. Catalog editing/versioning is out of scope. Once uploaded, a catalog is immutable in this MVP.

## Frontend architecture

Create a React application using TypeScript and Vite. Keep dependencies modest. Use React Router for application routes and TanStack Query (React Query) for server-state caching and mutations. Use plain React state for ephemeral selection and interaction state. Use SVG over the image for bounding boxes; do not add a canvas framework unless plain SVG demonstrably cannot meet a tested requirement.

Suggested routes:

- `/` redirects to the most recently opened project or the projects empty state.
- `/projects/:projectId/annotate` is the main annotation workspace.
- `/projects/new` creates a project.
- `/catalogs` lists reusable catalogs.
- `/catalogs/new` uploads a catalog.
- `/catalogs/:catalogId` shows catalog details.

Suggested frontend modules:

```text
frontend/src/
  api/
    client.ts
    projects.ts
    catalogs.ts
    annotations.ts
  components/
    AppShell.tsx
    ProjectSidebar.tsx
    BoundingBoxOverlay.tsx
    ImageNavigator.tsx
    ObjectInspector.tsx
    ReferenceClassBrowser.tsx
    ErrorNotice.tsx
  pages/
    AnnotationPage.tsx
    NewProjectPage.tsx
    CatalogListPage.tsx
    NewCatalogPage.tsx
    CatalogDetailPage.tsx
  types/
  test/
```

Do not mirror the backend database directly in component state. Keep API types explicit. Cache project summaries and catalogs. Fetch only the current image's annotations. Prefetch adjacent image metadata when helpful, but do not preload an entire large dataset into the browser.

Use native browser image loading and HTTP cache headers. Reference thumbnails must use `loading="lazy"` or equivalent. Search should be responsive; a local catalog-class index is acceptable for 89 classes, while the API must still support query and pagination for larger catalogs.

## Backend architecture

Add a FastAPI application around the existing domain modules. Prefer sync FastAPI endpoint functions for the current synchronous filesystem and SQLite work so FastAPI runs them in its threadpool. Avoid pretending blocking operations are asynchronous.

Suggested backend structure:

```text
annotate_tool/
  api/
    main.py
    dependencies.py
    errors.py
    routes/
      projects.py
      catalogs.py
      images.py
      annotations.py
      exports.py
    schemas/
      projects.py
      catalogs.py
      images.py
      annotations.py
  services/
    project_service.py
    catalog_service.py
    annotation_service.py
    export_service.py
  repositories/
    projects.py
    catalogs.py
    annotations.py
```

The exact file split may be adjusted to match the codebase, but route handlers must remain thin. Validation and business rules belong in services/domain functions; SQL belongs in repositories. Each unit needs a clear interface and isolated tests.

Create one app factory suitable for tests. Configure paths from environment variables. Use a lifespan hook to initialize the database, verify required directories, and surface a prominent warning/error when production is pointed at nonpersistent or unwritable storage.

Serve `/api/v1/...` for API routes, `/media/...` for controlled image delivery, and the compiled React SPA for all other non-API routes. Prevent arbitrary filesystem path access: media endpoints resolve only database-owned paths under the configured data root.

## API contract

Use JSON error bodies shaped consistently, for example:

```json
{
  "error": {
    "code": "catalog_invalid",
    "message": "Missing reference image for class 17",
    "details": {}
  }
}
```

At minimum implement:

### Health

- `GET /api/v1/health`
  - Returns application status, database availability, and writable-storage status.
  - Must not expose filesystem paths or secrets.

### Projects

- `GET /api/v1/projects?query=&limit=&offset=`
  - Returns all matching project summaries with thumbnail URL, image count, annotation count, reviewed count, and updated timestamp.
- `POST /api/v1/projects`
  - Multipart fields: `name`, `catalog_id`, `dataset_zip`.
  - Safely stages, validates, imports, indexes, and atomically publishes a project.
- `GET /api/v1/projects/{project_id}`
  - Returns project metadata and aggregate progress.
- `GET /api/v1/projects/{project_id}/images?limit=&offset=`
  - Returns ordered image summaries.
- `GET /api/v1/projects/{project_id}/images/{image_id}`
  - Returns image dimensions, media URL, ordered valid annotations, current class IDs, source names, status, and problem summary.
- `GET /api/v1/projects/{project_id}/export`
  - Returns a corrected-label ZIP built from immutable original labels plus current database decisions.

### Annotation decisions

- `PATCH /api/v1/annotations/{annotation_id}`
  - Body includes an action of `correct`, `relabel`, or `skip`, optional `target_class_id`, and optional `annotator_name`.
  - Validate that the annotation exists and belongs to a live project.
  - For `relabel`, validate that `target_class_id` exists in the project's attached catalog.
  - Update only that annotation's decision/current class in one short transaction.
  - Increment a version and return the authoritative updated annotation.
  - No client-supplied version is required for the MVP; concurrent writes are last-write-wins.

### Catalogs

- `GET /api/v1/catalogs?query=&limit=&offset=`
- `POST /api/v1/catalogs`
  - Multipart fields: `name`, `catalog_zip`.
- `GET /api/v1/catalogs/{catalog_id}`
- `GET /api/v1/catalogs/{catalog_id}/classes?query=&limit=&offset=`
  - Returns class IDs, names, and thumbnail URLs in numeric ID order unless searching.

Use appropriate 400, 404, 409, 413, and 422 responses. Enforce upload and expanded-archive limits on the backend regardless of frontend checks.

## Database model

Create a new schema rather than carrying forward the old project ownership model. Use idempotent migrations and foreign keys.

Recommended tables:

### `catalogs`

- `id` text primary key
- `name` text not null
- `storage_root` text not null
- `created_at` text not null

### `catalog_classes`

- `catalog_id` text not null, foreign key
- `class_id` integer not null, nonnegative
- `name` text not null
- `reference_path` text not null
- primary key (`catalog_id`, `class_id`)

### `projects`

- `id` text primary key
- `name` text not null
- `catalog_id` text not null, foreign key
- `dataset_root` text not null
- `created_at` text not null
- `updated_at` text not null

### `images`

- `id` text primary key
- `project_id` text not null, foreign key
- `relative_path` text not null
- `image_path` text not null
- `label_path` text not null
- `width` integer
- `height` integer
- `sort_index` integer not null
- `error_message` text
- unique (`project_id`, `relative_path`)

### `annotations`

- `id` text primary key
- `image_id` text not null, foreign key
- `line_index` integer not null
- `source_class_id` integer not null
- `current_class_id` integer not null
- `x_center`, `y_center`, `width`, `height` real not null
- four original coordinate-token fields or one lossless serialized coordinate-token value
- `original_line` text not null
- `decision` nullable text constrained to `correct`, `relabel`, or `skip`
- `annotator_name` nullable text
- `version` integer not null default 0
- `updated_at` nullable text
- unique (`image_id`, `line_index`)

### `import_problems`

- `project_id` text not null, foreign key
- `relative_path` text not null
- `line_index` nullable integer
- `message` text not null

The database is the canonical store for decisions, not mutable working label files. Keep uploaded/original labels immutable. Build exports by applying current annotation decisions to copies in memory or a temporary export directory using the existing lossless class-token replacement behavior. This avoids whole-file write races when two people edit different boxes in the same image.

Index project foreign keys, image ordering, decision status, and catalog class IDs/names where useful. Do not add speculative analytics tables.

## Filesystem layout

Use one configurable data root, defaulting to `./workspace_v2` locally:

```text
workspace_v2/
  app.sqlite3
  staging/
  catalogs/
    <catalog-id>/
      catalog.yaml
      images/
        <class-id>.<ext>
      .complete
  projects/
    <project-id>/
      dataset/
        images/
        labels/
        classes.txt or data.yaml
      backups/
        labels_original/
      .complete
  exports/
```

Publish imported catalogs/projects only after complete validation and database registration. Use same-filesystem atomic renames where possible. Startup may safely remove abandoned staging directories older than a conservative threshold, but must never delete completed project/catalog data automatically.

## Existing reference-catalog migration

Preserve only existing reference catalogs. Provide an idempotent CLI command such as:

```powershell
.\.venv\Scripts\python.exe -m annotate_tool.migrations.import_legacy_catalogs `
  --legacy-root .\workspace `
  --target-root .\workspace_v2
```

The migration must:

1. Read legacy registered reference classes and their image paths where available.
2. Validate every retained name/image pair using current catalog rules.
3. Create one reusable new catalog for each distinct legacy catalog.
4. Avoid duplicating a catalog when rerun; use a stable content fingerprint or an explicit migration record.
5. Copy reference images into the new catalog storage; do not depend on legacy project directories afterward.
6. Preserve sparse class IDs, Unicode names, and original supported image formats.
7. Leave legacy data untouched.
8. Ignore legacy datasets, decisions, progress, owners, and project records.
9. Produce a concise summary of imported, skipped, and failed catalogs.

Also retain the ability to upload `sample_data/sample_reference_catalog.zip` through the new API. Do not silently seed production data from developer-only paths.

## Performance requirements

Performance is a product requirement, not an optional polish step.

- A bounding-box click must update selected styling and the object inspector locally without a full-page navigation or API round trip.
- A class click must update optimistically and issue exactly one annotation mutation request.
- No annotation interaction may rescan the dataset directory, reopen every dataset image, or revalidate the catalog.
- Dataset parsing and image dimension discovery happen once at import and are persisted.
- Opening an image fetches only that image's annotations.
- Project lists return summaries from indexed database queries, not filesystem scans.
- Reference results are paginated or virtualized and thumbnails are lazy loaded.
- Static frontend assets use fingerprinted filenames and long-lived cache headers.
- Images/reference media use safe cache headers and conditional requests where practical.
- Locally, selection feedback should appear within one animation frame under ordinary load.
- Locally, a normal annotation save should complete within 300 ms at the 95th percentile in a representative automated or scripted benchmark, excluding deployment-network latency.
- Demonstrate that 20 concurrent clients saving different annotations do not cause database-lock errors under a basic load test. Keep transactions short; configure SQLite WAL and busy timeout.

Do not solve hypothetical scaling beyond this with PostgreSQL yet. If the concurrency test cannot pass reliably after reasonable SQLite tuning, stop and document the evidence before changing the approved architecture.

## Error handling and data integrity

- Validate all IDs and ownership relationships server-side even though there is no authentication.
- Reject path traversal, symlinks, duplicate case-insensitive archive destinations, oversized uploads, too many files, and excessive expanded archive size using the existing importer protections.
- Never accept a filesystem path from the browser as an authoritative storage path.
- Original uploads and original label backups remain immutable after successful import.
- Database decisions and export construction must never modify the originals.
- A failed save leaves the prior database state intact.
- A failed import leaves no visible project/catalog and no completed destination.
- A missing/corrupt media file returns a controlled error and records or exposes a project problem; it must not crash the API process.
- Frontend errors must distinguish retryable network/save failures from invalid uploads.
- Add global FastAPI exception translation and a React error boundary.
- Do not expose Python tracebacks, absolute server paths, or environment values in API responses.

## Testing requirements

### Preserve existing tests

Keep the current Python domain tests passing unless a test is explicitly tied only to the retired Streamlit presentation layer. Do not delete useful importer, YOLO, reference-catalog, storage, or workflow coverage. Replace Streamlit smoke coverage with API/frontend tests.

### Backend tests

Use pytest and FastAPI's test client. Cover at least:

- App startup and health.
- Empty project/catalog lists.
- Safe catalog upload and invalid catalog cases.
- Project import using a reusable saved catalog.
- Arbitrary and sparse source IDs.
- Unknown source ID display data.
- Sparse allowed target IDs.
- Target-ID enforcement.
- Current-image payload ordering and geometry.
- Correct, relabel, and skip mutations.
- Per-annotation last-write-wins behavior.
- Two annotations in the same label file updated independently.
- Export preserves geometry tokens and physical line ordering while replacing only selected class tokens.
- Import rollback and retry.
- Media path confinement.
- Legacy catalog-only migration and idempotent rerun.
- SQLite concurrent writes with representative short transactions.

### Frontend tests

Use Vitest and React Testing Library. Cover at least:

- Sidebar project search and selection.
- Client-side project navigation.
- Box selection updates without a network request.
- Correct selected/hover SVG styling.
- Coordinate scaling after responsive image resize.
- Previous/next image and object behavior.
- Reference search and lazy/paginated rendering.
- Optimistic relabel success.
- Optimistic relabel rollback and retry on API failure.
- Loading, empty, malformed-project, and network-error states.
- Narrow-screen sidebar behavior.

### End-to-end tests

Use Playwright for a small critical path:

1. Upload a reference catalog.
2. Create a project from the sample dataset.
3. See the project in the sidebar.
4. Open it and click a visible bounding box.
5. Select a sparse target class.
6. Navigate away and back; confirm the saved class persists.
7. Export and verify the corrected label token while geometry is unchanged.

Add a basic concurrency/load test for 20 clients updating different annotations. It may be a documented Python test script rather than a new load-testing framework.

## Deployment

Use a multi-stage Docker build:

1. Node stage installs locked frontend dependencies and runs tests/build.
2. Python stage installs locked backend dependencies.
3. Copy the compiled frontend into the FastAPI-served static directory.
4. Run one FastAPI/Uvicorn process suitable for the free-plan container.

Expose one configurable port and bind to `0.0.0.0`. Add a health check. Do not add a reverse proxy container for the MVP.

Required environment variables:

- `ANNOTATE_TOOL_DATA_DIR` — persistent mounted data directory.
- `PORT` — hosting platform port, with a sensible local default.
- Optional upload/import size limits using existing defaults.

Document clearly:

- The application loses uploaded data if `ANNOTATE_TOOL_DATA_DIR` is not backed by persistent storage.
- How to run locally for frontend development and as the combined production build.
- How to build and run the Docker image.
- How to run the legacy reference-catalog migration.
- How to back up the data directory.
- That no authentication exists and network access must be restricted by the deployment environment.

Do not claim CloudViu compatibility without verifying its actual build, port, persistent-volume, request-size, request-timeout, memory, and sleep/restart behavior. Keep deployment standards-based so the container can move to another host.

## Out of scope

- Authentication, passwords, SSO, invitations, roles, or permissions.
- Project ownership or assignment.
- Image/project locks.
- Real-time presence, cursors, WebSockets, or collaborative notifications.
- PostgreSQL, Redis, background queues, or object storage.
- Autoscaling or multiple backend replicas.
- Catalog editing, deletion, or versioning.
- Drawing, resizing, moving, or deleting bounding boxes.
- Creating new boxes.
- Segmentation, polygons, keypoints, or model-assisted labeling.
- Migrating legacy projects, datasets, decisions, progress, or ownership.
- Visual analytics beyond concise project progress.

## Delivery sequence

Implement in vertical, reviewable slices rather than writing the whole backend and frontend independently:

1. Add new database schema/repositories and catalog-only migration with tests.
2. Add FastAPI app, health, catalog APIs, and project-list API.
3. Add safe project import/indexing and current-image APIs.
4. Add per-annotation mutations and lossless export.
5. Scaffold React/Vite/TypeScript and build the application shell/sidebar.
6. Build the annotation workspace and SVG box interaction.
7. Build the reference-class browser and optimistic saves.
8. Add catalog/project creation screens.
9. Add end-to-end and concurrency tests.
10. Add the combined Docker build and deployment documentation.
11. Remove Streamlit from the production entry point only after the React/FastAPI critical path passes. Keeping the old Streamlit code temporarily during migration is acceptable; do not maintain two production UIs afterward.

Each slice must keep relevant tests green. Do not delete the working old UI until replacement behavior is demonstrably covered.

## Acceptance criteria

The migration is complete only when all of the following are demonstrated:

- The application launches as one FastAPI-served React service.
- Every user can see all projects in a persistent left sidebar.
- Users can switch projects without a browser reload.
- A box click selects the object immediately without a backend request.
- Selecting a class performs one optimistic per-annotation save.
- Multiple users can update different boxes in the same image without whole-label-file conflicts.
- Last write wins when the same annotation is updated concurrently.
- A reusable saved catalog can be attached to multiple projects.
- Only catalog IDs are accepted as output class IDs.
- Arbitrary nonnegative source IDs are accepted and unknown IDs are displayed clearly.
- Existing reference catalogs can be migrated idempotently; legacy datasets/progress are not migrated.
- Original labels remain unchanged.
- Export changes only approved class tokens and preserves geometry/order.
- Project/image/catalog browsing does not rescan all files on ordinary interactions.
- The sample end-to-end workflow passes.
- Backend, frontend, and end-to-end test suites pass.
- The 20-client representative write test completes without database-lock errors.
- Docker build succeeds and the container passes its health check.
- Restarting with the same persistent data directory preserves catalogs, projects, and saved decisions.
- Restarting without persistent storage is documented as unsafe rather than silently presented as durable.

When implementation is finished, report the final architecture, migration command, run/deployment commands, test results, performance/concurrency evidence, and any remaining hosting limitation that requires confirmation from CloudViu.
