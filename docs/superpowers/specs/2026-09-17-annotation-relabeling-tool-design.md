# Annotation Relabeling Tool Design

## Goal

Build a small internal Streamlit web application for rapidly reviewing and correcting class IDs in existing YOLO object-detection annotations. The application must preserve bounding-box coordinates, save every completed decision immediately, survive browser or application restarts, and remain simple enough to build and maintain within four days.

## Scope

The MVP supports importing an assigned YOLO dataset, viewing existing boxes, selecting an object, inspecting an enlarged crop, confirming its current class, changing it through a searchable visual class grid, navigating images and objects, tracking progress, and exporting corrected labels.

It does not create, resize, or delete boxes. It does not provide authentication, automated classification, model inference, analytics, or a separate API/frontend stack.

## Deployment Model

The application is a single Streamlit process hosted on a persistent company machine and exposed on the internal network, normally at `http://<server-ip>:8501`.

Annotators upload one ZIP archive from their laptop. The archive contains:

```text
images/
labels/
data.yaml or classes.txt
references/
```

The server extracts each import into an isolated, generated dataset directory. A human-readable assignment name and a generated internal ID prevent accidental path collisions. Upload and extraction limits are configurable because image datasets may be large.

## Architecture

```text
app.py                         Streamlit UI and session orchestration
annotate_tool/config.py        Paths and configurable limits
annotate_tool/importer.py      ZIP validation and safe extraction
annotate_tool/dataset.py       Dataset discovery and class metadata
annotate_tool/yolo.py          Annotation parsing and class-only edits
annotate_tool/rendering.py     Numbered image overlays and crops
annotate_tool/storage.py       Backups, atomic writes, and exports
annotate_tool/progress.py      SQLite registry and review progress
tests/                         Unit and integration tests
sample_data/                   Small development dataset
```

Modules remain small and purpose-specific, but the application uses direct function calls rather than service layers or an API.

## Persistent Storage

Dataset content stays on the filesystem:

```text
workspace/
  assignments/
    <generated-id>/
      source_name.txt
      images/
      labels/
      references/
      data.yaml or classes.txt
      backups/
        labels_original/
```

SQLite stores only application metadata:

- dataset ID, display name, import state, and timestamps;
- reviewed-object decisions and resume position;
- skipped objects and import/runtime problems.

YOLO label files remain the source of truth for corrected annotations. SQLite runs in WAL mode and uses short transactions. It is local to the persistent application workspace and requires no database service.

## Import and Validation

The importer accepts ZIP files only. It rejects absolute paths, parent traversal, symlinks, duplicate destinations, excessive uncompressed size, and excessive file counts before extraction. Extraction occurs in a temporary directory and is moved into the assignments directory only after validation succeeds.

A valid import needs `images/` and class metadata. `labels/` and `references/` may contain missing items, which are reported in the UI rather than crashing the import. Class metadata is read from `data.yaml` or `classes.txt`; the application expects exactly 89 class entries with IDs 0 through 88. Reference images map deterministically by numeric stem, such as `references/27.jpg`. Common image extensions are accepted.

Before an assignment becomes editable, the application copies its initial `labels/` tree to `backups/labels_original/`. Creation uses an exclusive marker/transaction so the backup is made once and is never overwritten.

## Annotation Model and Safe Writes

Each valid YOLO line is parsed as a class token followed by exactly four finite normalized coordinates. The parser retains the original coordinate tokens as text. Relabeling replaces only the first token on the selected line; it does not reserialize coordinates.

Every edit follows this order:

1. Revalidate the selected dataset, image, label path, line index, and expected current line.
2. Write the complete updated label content to a temporary file in the same directory.
3. Flush and atomically replace the working label file.
4. Record the completed decision in SQLite.
5. Advance to the next unreviewed object.

If file persistence succeeds but the SQLite update is interrupted, startup reconciliation treats the label file as authoritative and leaves the object available for review again. Repeating the same class decision is safe. A malformed file is never rewritten.

The Correct action records progress without changing the label file. A class-card action edits the class ID and then records progress. A decision not yet clicked is intentionally unsaved and remains unreviewed after a crash.

## Object Identity

Within the MVP, an object is identified by dataset ID, normalized image-relative path, and zero-based annotation line index. Because the tool never adds, removes, or reorders boxes, this identity remains stable. The current line content is checked before any edit to prevent a stale Streamlit rerun from changing the wrong object.

## User Interface

The sidebar contains ZIP import, assignment selection, import status, dataset health, and export controls.

The main page uses two columns:

- The left column shows the full image with numbered boxes, image navigation, progress, and numbered object-selection buttons. Numbered buttons are preferred over clickable canvas dependencies for reliability.
- The right column shows the selected object number, current class ID/name, a padded enlarged crop, a large Correct button, Skip and object navigation controls, class search, and visual class cards.

Each class card shows its reference image when available, class name, numeric ID, and a selection button. Search matches class names case-insensitively and accepts numeric IDs. Missing reference images use a clear placeholder.

Correct and class selection save immediately and advance to the next unreviewed object, continuing into the next image when needed. Manual previous/next navigation remains available. Enter-to-confirm is included only if it can be implemented without an unsafe or fragile third-party component.

Progress shows image position, object position, reviewed count, and overall percentage. When an assignment is reopened, the application resumes at the first unreviewed object. Images with no valid objects remain navigable.

## Multi-Annotator Model

The MVP avoids authentication, browser-session tracking, and dynamic task claiming. Each import creates an isolated assignment, and annotators choose their assigned dataset from a dropdown. The UI states that each assignment must belong to one annotator at a time; assignment ownership is an operational rule rather than an application lock.

This constraint is explicit in the README and UI. SQLite prevents progress-file write conflicts, while stale-line validation prevents silent annotation corruption.

## Error Handling

User-facing errors identify the affected file and provide a safe next action. The application handles:

- unreadable or unsupported ZIP archives;
- unsafe archive entries and invalid dataset layouts;
- missing, empty, or malformed label files;
- unreadable images;
- non-finite or out-of-range YOLO values;
- class IDs outside 0–88;
- class mapping or reference-image mismatches;
- interrupted imports or writes;
- unavailable persistent storage.

Invalid annotations are excluded from editing and recorded as problems. The rest of the assignment remains usable where safe.

## Export and Recovery

Annotators can download a ZIP containing corrected `labels/`, class metadata, progress summary, and a problem report. Images are excluded by default to keep exports small. Original backups are never included as working output and are never modified.

Browser closure, refresh, or Streamlit restart loses only UI state. Completed decisions and corrected labels persist on the server. Protection from complete server-disk loss is an infrastructure responsibility; the deployment documentation requires persistent storage and recommends scheduled machine-level backups.

## Dependencies

Runtime dependencies are limited to Streamlit, Pillow, and PyYAML. SQLite uses Python's standard library. Pytest is the development/test dependency.

No React, FastAPI, PostgreSQL, Redis, Docker orchestration, or custom canvas library is introduced.

## Testing and Verification

Automated tests cover:

- YOLO coordinate conversion and exact crop bounds;
- multiple boxes per image;
- preservation of coordinate-token text during relabeling;
- Correct leaving label content unchanged;
- immutable one-time backups;
- atomic save behavior and stale-line rejection;
- SQLite progress persistence and restart resume;
- safe ZIP validation and traversal rejection;
- empty, missing, and malformed labels;
- unreadable images and invalid class IDs;
- deterministic class/reference mapping;
- class-name and class-ID search;
- corrected-label export content.

A generated sample assignment includes valid multi-box images plus empty, missing, and malformed-label cases. Final verification runs the full test suite and launches Streamlit against this dataset for visual inspection of overlays, crops, navigation, class filtering, immediate save, restart recovery, and export.

## Definition of Done

An annotator can open the internal web application, import or reopen an assigned dataset, select an existing object, inspect its crop and current class, confirm or change the class with one action, continue automatically, close and resume later, and export corrected labels. Coordinates and the immutable original-label backup remain unchanged throughout the workflow.
