# Project Based Annotation Platform Design

## Purpose

Evolve the current Streamlit relabeling MVP into a persistent internal project system for a team. An administrator uploads a dataset and its reference catalog once. Annotators then open assigned projects from a server-side list, click bounding boxes directly in the image, and save class decisions immediately.

This remains a focused YOLO class-correction tool. It does not attempt to reproduce the general annotation, training, analytics, authentication, or collaboration features of Roboflow or Ultralytics.

## Decisions

- Keep Python and Streamlit.
- Use SQLite for structured metadata, ownership, progress, audit records, and schema migrations.
- Keep images, labels, immutable backups, and reference images in persistent server file storage rather than database blobs.
- Let many annotators work concurrently, but assign each dataset to one annotator at a time.
- Give every project its own reference catalog.
- Treat reference catalog IDs as the only valid relabeling output IDs.
- Accept arbitrary nonnegative source class IDs and any source class count.
- Replace the numbered object-button list with directly clickable bounding boxes.
- Preserve the existing atomic label-update and immutable-backup guarantees.

## Storage Layout

The configured `ANNOTATE_TOOL_DATA_DIR` remains the persistent root:

```text
workspace/
  app.db
  projects/
    <project_id>/
      dataset/
        images/
        labels/
        data.yaml or classes.txt
        backups/
          labels_original/
      references/
        catalog.yaml
        images/
          <class_id>.<image_extension>
  staging/
```

The application must not use temporary or ephemeral deployment storage for this root. Operations documentation will continue to require machine-level backups.

SQLite will store paths relative to the persistent root where practical. Binary images and ZIP payloads will not be stored in SQLite.

## Data Model

### Projects

A project record contains:

- stable project ID;
- display name;
- dataset root;
- status;
- assigned annotator name, if any;
- creation timestamp;
- source filename;
- reference-catalog status.

### Reference Classes

Each project has zero or more reference-class records containing:

- project ID;
- nonnegative class ID;
- display name;
- server-side reference-image path;
- deterministic display order.

Class IDs need not be contiguous. Only IDs with valid reference records and readable images are valid relabeling targets. A missing or invalid reference catalog blocks annotation and produces an actionable project error rather than exposing an empty class selector.

### Annotators and Ownership

The MVP uses a simple annotator-name selector rather than a full authentication system. An administrator assigns one annotator name to each project. The project list shows ownership and prevents a different selected annotator from editing that project.

This is an operational ownership control, not security-grade identity verification. Authentication and role management remain out of scope.

### Progress and Audit

Existing object decisions remain keyed by project, image path, and physical label-line index. Each decision also records the selected annotator name, previous class ID, resulting class ID, action, and timestamp.

Existing assignment and decision rows will be migrated in place. Their assignment IDs become project IDs, and existing paths and progress remain valid.

## Import Workflow

An administrator creates a project through the web app and supplies:

1. a dataset ZIP containing `images/`, optional `labels/`, and optional source class metadata; and
2. a project reference catalog.

The first reference catalog will be generated from `HAIR_SKU_product_images.docx`. The document contains 89 table cells with one image and one name per product. Reading order is left-to-right and top-to-bottom, mapping to IDs `0` through `88`.

For repeatable future imports, the normal catalog format will be a ZIP:

```text
catalog.yaml
references/
  0.png
  1.jpg
  7.webp
```

`catalog.yaml` maps numeric IDs to display names. The IDs may be sparse. The image filename stem must match its catalog ID. DOCX conversion is an administrative preparation step for the supplied catalog, not a general DOCX parsing feature in the deployed MVP.

Import validation occurs before the project becomes visible:

- archive safety and expanded-size limits;
- required images directory;
- readable image files;
- safe YOLO label paths;
- valid reference catalog IDs and names;
- exactly one readable reference image per target ID;
- immutable original-label backup completion.

If validation fails, the incomplete project is removed and no project row is registered.

## Source Class Handling

Source labels may contain any nonnegative integer class ID. Source class metadata is descriptive only and does not restrict loading:

- a `names` list maps indices to names;
- a numeric-keyed dictionary may be sparse and may contain any number of IDs;
- `classes.txt` maps line numbers to names;
- missing metadata or an unmapped source ID displays `Unknown source class <id>`.

Negative or non-integer class tokens remain malformed. Coordinate validation remains unchanged. A source ID without a target reference can still be viewed and must be relabeled to one of the reference-defined target IDs.

The Correct action is enabled only when the current source ID is a valid target reference ID. Otherwise, the annotator must relabel or skip the object.

## Clickable Bounding Box Component

The original image area will use an inline Streamlit custom component based on the installed Streamlit components-v2 API. No third-party image-coordinate dependency is required.

Python sends the component:

- a base64-encoded rendered image;
- stable object keys;
- bounding-box pixel coordinates;
- visible box numbers;
- the selected object key.

The component renders the image and an SVG overlay in the same responsive container. Each SVG rectangle is clickable across its full box area. Clicking sends the stable object key to Python as a trigger value, updates the current cursor, and reruns the app. The selected rectangle uses a distinct color and width. Hover styling indicates that boxes are interactive.

Coordinates scale with the displayed image using the SVG `viewBox`; hit testing therefore remains aligned when the browser resizes. The component receives data values rather than interpolating dataset text into trusted HTML or JavaScript.

The existing object buttons will be removed. Previous and next object/image navigation remains available as a fallback and for rapid keyboard-oriented review.

## Application Screens and Flow

### Project List

The sidebar presents persistent projects with project name, owner, item count, and progress. Selecting an accessible project opens it without another upload.

### Administrative Import

An import panel creates a project and uploads the dataset and reference-catalog ZIPs once. The MVP does not implement security-grade administrator authentication. Deployment may restrict access to the internal network and use operational policy for the import panel.

### Annotation

1. The annotator selects their name.
2. The sidebar shows their assigned projects and read-only status for projects assigned to others.
3. The annotator opens a project.
4. The full image displays clickable numbered boxes.
5. Clicking a box shows its crop and current source class.
6. Correct preserves the class only if it is a valid target reference ID.
7. Clicking a reference card replaces only the class token and advances to the next unreviewed object.
8. Skip records no label change and advances according to the existing workflow.

## Concurrency and Data Safety

Dataset-level ownership is the MVP concurrency boundary. Different annotators may edit different projects simultaneously. The UI refuses edits when the selected annotator does not own the project.

The system does not support multiple annotators editing one project concurrently. Object-level claims, distributed locks, and conflict resolution remain future work.

Within an owned project:

- every relabel checks the expected original line before writing;
- coordinates are preserved byte-for-byte;
- label replacement remains atomic;
- the immutable original backup is never overwritten;
- progress is recorded only after a successful label write;
- failures remain visible and do not silently mark work complete.

## Migration

A numbered SQLite schema migration will:

- extend existing assignments into projects;
- add annotator ownership fields;
- add reference-class records;
- add annotator identity to new decisions while preserving old decisions;
- retain existing project IDs, file paths, backups, and progress.

The currently imported hair assignment will receive the extracted 89-image reference catalog without re-importing or changing its working labels.

Migration must be transactional and idempotent. Startup may retry it safely after interruption.

## Error Handling

The UI will distinguish:

- invalid project import;
- missing or invalid reference catalog;
- source-class metadata warnings;
- malformed YOLO coordinates or class tokens;
- unreadable images;
- assignment ownership restrictions;
- concurrent or stale label changes;
- storage and database failures.

Project-fatal errors stop editing that project. Per-image or per-label errors are recorded in Problems and do not stop healthy files from being reviewed.

## Testing

Automated coverage will include:

- arbitrary, sparse, and unmapped nonnegative source IDs;
- negative and non-integer source IDs;
- target IDs derived only from the reference catalog;
- missing, duplicate, mismatched, and unreadable reference images;
- Correct disabled for source IDs outside the target catalog;
- relabeling arbitrary source IDs to sparse target IDs while preserving coordinates;
- direct box-click selection and selected-box highlighting;
- responsive coordinate alignment logic;
- dataset ownership and unauthorized edit prevention;
- database migration from the existing schema;
- preservation of existing progress and backups;
- project import rollback;
- full Streamlit smoke flow.

The supplied hair dataset and converted reference catalog will be used for an integration check after unit and UI tests pass.

## Deployment Boundary

The MVP targets one persistent company server and an internal network. It supports many simultaneous users working on different projects. It does not provide high availability, cloud object storage, PostgreSQL, external identity providers, or multi-server coordination.

If usage later requires multiple application servers or multiple annotators per project, the natural upgrade is PostgreSQL plus shared object storage and object-level work claiming. That infrastructure is deliberately deferred.

## Acceptance Criteria

- An administrator imports a dataset and reference catalog once.
- The project remains available after browser and server restarts.
- Different projects may use different target reference catalogs.
- Any nonnegative input class ID can be displayed and reviewed.
- Only reference-catalog IDs can be written as output classes.
- A user selects an object by clicking its bounding box in the full image.
- No row of per-object selection buttons is shown.
- One annotator owns and edits a project at a time.
- Multiple annotators can use different projects concurrently.
- Existing assignments, working labels, backups, and progress survive migration.
- Relabeling changes only the class token and saves immediately.
