# Annotation Relabeling Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-process Streamlit web app that imports isolated YOLO datasets, lets an annotator confirm or change existing object classes with immediate persistence, resumes progress after restarts, and exports corrected labels.

**Architecture:** Dataset files live in isolated assignment directories, while SQLite stores the assignment registry and review decisions. Focused Python modules own safe ZIP import, YOLO parsing/editing, rendering, progress, navigation, and export; `app.py` composes those modules into a two-column Streamlit interface without a separate API.

**Tech Stack:** Python 3.11+, Streamlit, Pillow, PyYAML, standard-library SQLite/ZIP/file APIs, pytest

**Spec:** `docs/superpowers/specs/2026-09-17-annotation-relabeling-tool-design.md`

## Global Constraints

- The runtime is one Streamlit process; do not add React, FastAPI, PostgreSQL, Redis, Docker orchestration, custom canvas libraries, or authentication.
- Accept one ZIP per assignment containing `images/`, `labels/`, `references/`, and either `data.yaml` or `classes.txt`; allow one enclosing top-level directory.
- Expect exactly 89 class names with IDs `0` through `88`; reference images map by numeric filename stem.
- Keep YOLO label files as annotation source of truth and replace only the selected line's first token when relabeling.
- Never overwrite `backups/labels_original/`; create it before an assignment becomes editable.
- Persist completed decisions immediately; a browser refresh or Streamlit restart may lose only undecided UI state.
- Use SQLite WAL mode and short transactions for metadata and progress.
- One assignment belongs to one annotator at a time; the MVP does not implement distributed locking or task claiming.
- Invalid inputs must produce understandable problems and must never trigger silent label rewrites.
- Use atomic same-directory temporary-file replacement for label edits.
- Exports contain corrected labels, class metadata, progress summary, and problem report; exclude images and original backups.

## File Structure

```text
app.py                                  Streamlit composition and widgets
annotate_tool/__init__.py               Package marker and version
annotate_tool/config.py                 Workspace paths and import limits
annotate_tool/models.py                 Shared immutable dataclasses
annotate_tool/yolo.py                   Parse, validate, locate, and render YOLO boxes
annotate_tool/importer.py               Safe ZIP inspection/extraction and backup
annotate_tool/progress.py               SQLite schema and progress repository
annotate_tool/dataset.py                Assignment loading and class/reference mapping
annotate_tool/rendering.py              Box overlay, crop, and missing-reference image
annotate_tool/storage.py                Atomic relabel and corrected-label export
annotate_tool/workflow.py               Navigation and review orchestration
scripts/create_sample_data.py           Reproducible sample ZIP generator
.streamlit/config.toml                  Upload and server defaults
requirements.txt                        Runtime dependencies
requirements-dev.txt                    Test dependencies
README.md                               Setup, operation, and recovery guidance
tests/conftest.py                        Shared dataset/image fixtures
tests/test_yolo.py                       Parser and coordinate tests
tests/test_importer.py                   ZIP and backup tests
tests/test_progress.py                   SQLite persistence tests
tests/test_dataset_rendering.py          Dataset mapping, overlays, and crops
tests/test_storage.py                    Atomic relabel and export tests
tests/test_workflow.py                   Review/navigation tests
tests/test_app_smoke.py                  Streamlit AppTest happy-path test
```

---

### Task 1: Project Foundation and Lossless YOLO Parsing

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `annotate_tool/__init__.py`
- Create: `annotate_tool/models.py`
- Create: `annotate_tool/yolo.py`
- Create: `tests/test_yolo.py`

**Interfaces:**
- Consumes: no project interfaces.
- Produces: `Annotation`, `AnnotationProblem`, `ParseResult`, `parse_label_text(text, expected_classes=89)`, `box_pixels(annotation, image_size)`, `replace_class_token(text, line_index, expected_line, new_class_id)`.

- [ ] **Step 1: Add dependency manifests and package metadata**

Create `requirements.txt`:

```text
streamlit>=1.39,<2
Pillow>=10,<12
PyYAML>=6,<7
```

Create `requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8,<9
```

Create `annotate_tool/__init__.py`:

```python
"""Internal YOLO annotation relabeling tool."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Write failing parser, pixel-bound, and lossless-edit tests**

Create `tests/test_yolo.py` with tests equivalent to:

```python
import pytest

from annotate_tool.yolo import box_pixels, parse_label_text, replace_class_token


def test_parse_retains_coordinate_tokens():
    result = parse_label_text("42 0.522 0.433 0.135 0.271\n")
    assert result.problems == ()
    annotation = result.annotations[0]
    assert annotation.class_id == 42
    assert annotation.coordinate_tokens == ("0.522", "0.433", "0.135", "0.271")
    assert annotation.line_index == 0


def test_parser_reports_bad_lines_without_returning_editable_annotation():
    result = parse_label_text("89 0.5 0.5 0.2 0.2\n3 nope 0.5 0.2 0.2\n")
    assert result.annotations == ()
    assert [problem.line_index for problem in result.problems] == [0, 1]


def test_box_pixels_clamps_edges_and_uses_floor_ceil():
    annotation = parse_label_text("2 0.10 0.10 0.40 0.40\n").annotations[0]
    assert box_pixels(annotation, (100, 50)) == (0, 0, 30, 15)


def test_replace_class_changes_only_first_token():
    original = "42 0.522 0.433 0.135 0.271\n7 0.1 0.2 0.3 0.4\n"
    updated = replace_class_token(original, 0, "42 0.522 0.433 0.135 0.271", 17)
    assert updated == "17 0.522 0.433 0.135 0.271\n7 0.1 0.2 0.3 0.4\n"


def test_replace_class_rejects_stale_line():
    with pytest.raises(ValueError, match="changed since it was loaded"):
        replace_class_token("3 0.5 0.5 0.2 0.2\n", 0, "4 0.5 0.5 0.2 0.2", 6)
```

- [ ] **Step 3: Run the tests and verify the missing-module failure**

Run: `python -m pytest tests/test_yolo.py -v`

Expected: collection fails with `ModuleNotFoundError` for `annotate_tool.yolo`.

- [ ] **Step 4: Implement shared models and YOLO functions**

Create frozen dataclasses in `annotate_tool/models.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Annotation:
    class_id: int
    coordinate_tokens: tuple[str, str, str, str]
    coordinates: tuple[float, float, float, float]
    line_index: int
    original_line: str


@dataclass(frozen=True)
class AnnotationProblem:
    line_index: int | None
    message: str
    path: Path | None = None


@dataclass(frozen=True)
class ParseResult:
    annotations: tuple[Annotation, ...]
    problems: tuple[AnnotationProblem, ...]
```

Implement these exact interfaces in `annotate_tool/yolo.py`: `parse_label_text(text: str, expected_classes: int = 89) -> ParseResult`, `box_pixels(annotation: Annotation, image_size: tuple[int, int]) -> tuple[int, int, int, int]`, and `replace_class_token(text: str, line_index: int, expected_line: str, new_class_id: int, expected_classes: int = 89) -> str`.

Parsing rules: ignore blank lines; require exactly five whitespace-separated tokens; parse integer class IDs; require finite floats; require centers in `[0, 1]`, widths/heights in `(0, 1]`; reject class IDs outside `0..expected_classes-1`; preserve the stripped original line and four coordinate-token strings. `box_pixels` uses floor for left/top, ceil for right/bottom, and clamps to image edges.

- [ ] **Step 5: Run parser tests**

Run: `python -m pytest tests/test_yolo.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit the parser increment**

```powershell
git add requirements.txt requirements-dev.txt annotate_tool/__init__.py annotate_tool/models.py annotate_tool/yolo.py tests/test_yolo.py
git commit -m "feat: add lossless YOLO annotation parsing"
```

---

### Task 2: Safe Assignment Import and Immutable Backup

**Files:**
- Create: `annotate_tool/config.py`
- Create: `annotate_tool/importer.py`
- Create: `tests/test_importer.py`

**Interfaces:**
- Consumes: `AnnotationProblem` from Task 1.
- Produces: `AppPaths.from_root(root)`, `ImportLimits`, `ImportedAssignment`, `inspect_archive(zip_path, limits)`, `import_assignment(zip_path, display_name, paths, limits)`, and `ensure_original_backup(assignment_root)`.

- [ ] **Step 1: Write failing tests for archive safety and backup immutability**

Create helpers that build ZIP files in `tests/test_importer.py`, then cover:

```python
def test_import_accepts_single_wrapper_directory(tmp_path):
    archive = make_zip(tmp_path, {
        "batch/images/a.jpg": b"image-bytes",
        "batch/labels/a.txt": b"1 0.5 0.5 0.2 0.2\n",
        "batch/classes.txt": classes_text().encode(),
    })
    paths = AppPaths.from_root(tmp_path / "runtime")
    imported = import_assignment(archive, "Alice batch", paths, ImportLimits())
    assert (imported.root / "images/a.jpg").exists()
    assert (imported.root / "backups/labels_original/a.txt").read_bytes().startswith(b"1 ")


@pytest.mark.parametrize("member", ["../escape.txt", "/absolute.txt", "C:/drive.txt"])
def test_import_rejects_unsafe_paths(tmp_path, member):
    archive = make_zip(tmp_path, {member: b"bad"})
    with pytest.raises(AssignmentImportError, match="unsafe archive path"):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "runtime"), ImportLimits())


def test_existing_backup_is_never_overwritten(tmp_path):
    assignment = create_assignment_tree(tmp_path)
    ensure_original_backup(assignment)
    (assignment / "labels/a.txt").write_text("9 0.5 0.5 0.2 0.2\n")
    ensure_original_backup(assignment)
    assert (assignment / "backups/labels_original/a.txt").read_text().startswith("1 ")
```

Also test duplicate normalized paths, symlink entries, excessive file count, excessive total uncompressed bytes, missing `images/`, missing class metadata, blank display names, and cleanup after failed import.

- [ ] **Step 2: Run importer tests and verify failure**

Run: `python -m pytest tests/test_importer.py -v`

Expected: collection fails because `annotate_tool.importer` and `annotate_tool.config` do not exist.

- [ ] **Step 3: Implement configuration dataclasses**

Create `annotate_tool/config.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    assignments: Path
    database: Path
    staging: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        resolved = root.resolve()
        return cls(resolved, resolved / "assignments", resolved / "progress.sqlite3", resolved / "staging")

    def ensure(self) -> None:
        self.assignments.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ImportLimits:
    max_files: int = 25_000
    max_uncompressed_bytes: int = 20 * 1024**3
```

- [ ] **Step 4: Implement inspected, staged ZIP import**

Create `annotate_tool/importer.py` with:

```python
@dataclass(frozen=True)
class ImportedAssignment:
    assignment_id: str
    display_name: str
    root: Path
    class_metadata_path: Path


class AssignmentImportError(ValueError):
    pass


```

Add the exact interfaces `inspect_archive(zip_path: Path, limits: ImportLimits) -> tuple[str, ...]`, `ensure_original_backup(assignment_root: Path) -> Path`, and `import_assignment(zip_path: Path, display_name: str, paths: AppPaths, limits: ImportLimits) -> ImportedAssignment`.

Use `zipfile.ZipFile.infolist()` before extraction. Normalize each member with `PurePosixPath`; reject absolute paths, drive-like prefixes, `..`, symlink mode bits, duplicate case-folded destinations, too many files, and excessive total size. Strip one common wrapper directory only when the archive root does not itself contain `images/`. Extract each regular file by streaming to a generated staging directory, validate structure, create the immutable backup using an exclusive `.backup_complete` marker, then move the validated directory into `assignments/<uuid>` with `os.replace`. Always remove failed staging directories.

- [ ] **Step 5: Run importer tests**

Run: `python -m pytest tests/test_importer.py -v`

Expected: all tests pass and no file appears outside the temporary runtime directory.

- [ ] **Step 6: Commit the importer increment**

```powershell
git add annotate_tool/config.py annotate_tool/importer.py tests/test_importer.py
git commit -m "feat: import assignments with immutable backups"
```

---

### Task 3: SQLite Assignment Registry and Durable Progress

**Files:**
- Create: `annotate_tool/progress.py`
- Create: `tests/test_progress.py`

**Interfaces:**
- Consumes: `ImportedAssignment` from Task 2.
- Produces: `AssignmentRecord`, `ReviewDecision`, and `ProgressRepository` methods `initialize`, `register_assignment`, `list_assignments`, `record_decision`, `list_decisions`, `reviewed_keys`, `summary`, `record_problem`, and `list_problems`.

- [ ] **Step 1: Write failing repository tests**

Create `tests/test_progress.py` covering restart persistence and idempotency:

```python
def test_decisions_survive_repository_restart(tmp_path):
    database = tmp_path / "progress.sqlite3"
    repo = ProgressRepository(database)
    repo.initialize()
    repo.register_assignment("id-1", "Alice", tmp_path / "assignment")
    repo.record_decision("id-1", "images/a.jpg", 2, "correct", 7, 7)

    reopened = ProgressRepository(database)
    reopened.initialize()
    assert reopened.reviewed_keys("id-1") == {("images/a.jpg", 2)}
    assert reopened.summary("id-1") == {"reviewed": 1, "correct": 1, "relabel": 0, "skipped": 0}


def test_recording_same_object_updates_one_row(tmp_path):
    repo = prepared_repository(tmp_path)
    repo.record_decision("id-1", "images/a.jpg", 0, "skip", 4, None)
    repo.record_decision("id-1", "images/a.jpg", 0, "relabel", 4, 8)
    assert repo.summary("id-1")["reviewed"] == 1
    assert repo.summary("id-1")["relabel"] == 1
```

Also test assignment listing order, duplicate registration, allowed decision values, problem persistence, foreign-key enforcement, and database creation in a missing parent directory.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_progress.py -v`

Expected: collection fails because `annotate_tool.progress` does not exist.

- [ ] **Step 3: Implement schema and repository**

Create `annotate_tool/progress.py` with frozen `AssignmentRecord` and `ReviewDecision` dataclasses. `ProgressRepository` exposes the exact methods `__init__(database_path: Path)`, `initialize() -> None`, `register_assignment(assignment_id: str, display_name: str, root: Path) -> None`, `list_assignments() -> tuple[AssignmentRecord, ...]`, `record_decision(assignment_id: str, image_path: str, line_index: int, decision: Literal["correct", "relabel", "skip"], previous_class_id: int, resulting_class_id: int | None) -> None`, `list_decisions(assignment_id: str) -> tuple[ReviewDecision, ...]`, `reviewed_keys(assignment_id: str) -> set[tuple[str, int]]`, `summary(assignment_id: str) -> dict[str, int]`, `record_problem(assignment_id: str, path: str, message: str) -> None`, and `list_problems(assignment_id: str) -> tuple[tuple[str, str], ...]`.

Each connection enables `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and `PRAGMA busy_timeout=5000`. Use this conflict target for idempotent decisions: `INSERT INTO decisions (assignment_id, image_path, line_index, decision, previous_class_id, resulting_class_id, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(assignment_id, image_path, line_index) DO UPDATE SET decision=excluded.decision, previous_class_id=excluded.previous_class_id, resulting_class_id=excluded.resulting_class_id, decided_at=excluded.decided_at`. Give problems a unique `(assignment_id, path, message)` constraint and use `INSERT OR IGNORE` so Streamlit reruns do not duplicate them. Treat `skip` as not reviewed in `reviewed_keys`, but report it separately in `summary`.

- [ ] **Step 4: Run progress tests**

Run: `python -m pytest tests/test_progress.py -v`

Expected: all tests pass.

- [ ] **Step 5: Commit the progress increment**

```powershell
git add annotate_tool/progress.py tests/test_progress.py
git commit -m "feat: persist assignments and review progress"
```

---

### Task 4: Dataset Loading, Class Mapping, Overlays, and Crops

**Files:**
- Modify: `annotate_tool/models.py`
- Create: `annotate_tool/dataset.py`
- Create: `annotate_tool/rendering.py`
- Create: `tests/conftest.py`
- Create: `tests/test_dataset_rendering.py`

**Interfaces:**
- Consumes: YOLO parser/models from Task 1 and assignment roots from Task 2.
- Produces: `ClassInfo`, `ImageRecord`, `AssignmentDataset`, `load_assignment(root)`, `filter_classes(classes, query)`, `draw_numbered_boxes(image, annotations, selected_index)`, `crop_annotation(image, annotation, padding_ratio=0.15)`, and `reference_placeholder(class_info)`.

- [ ] **Step 1: Add reusable dataset fixtures and failing tests**

Create `tests/conftest.py` fixtures that use Pillow to make a `100x80` image, 89 class names, numeric reference images, and label files. Create `tests/test_dataset_rendering.py` with:

```python
def test_load_assignment_maps_images_labels_classes_and_references(dataset_root):
    dataset = load_assignment(dataset_root)
    assert len(dataset.classes) == 89
    assert dataset.classes[3].name == "Product 03"
    assert dataset.classes[3].reference_path.name == "3.jpg"
    assert dataset.images[0].relative_path == "images/a.jpg"
    assert len(dataset.images[0].parse_result.annotations) == 2


def test_search_matches_name_and_exact_numeric_id(dataset_root):
    classes = load_assignment(dataset_root).classes
    assert [item.class_id for item in filter_classes(classes, "product 08")] == [8]
    assert [item.class_id for item in filter_classes(classes, "17")] == [17]


def test_crop_matches_box_with_clamped_padding(dataset_root):
    record = load_assignment(dataset_root).images[0]
    with Image.open(record.path) as image:
        crop = crop_annotation(image, record.parse_result.annotations[0], padding_ratio=0)
    assert crop.size == (20, 16)


def test_overlay_draws_without_mutating_original(dataset_root):
    record = load_assignment(dataset_root).images[0]
    with Image.open(record.path) as image:
        before = image.tobytes()
        rendered = draw_numbered_boxes(image, record.parse_result.annotations, 0)
        assert image.tobytes() == before
        assert rendered.tobytes() != before
```

Also cover YAML list/dict `names` formats, `classes.txt`, duplicate/missing class IDs, missing references, nested image paths, missing/empty labels, corrupt images, and malformed annotation problems.

- [ ] **Step 2: Run dataset/rendering tests and verify failure**

Run: `python -m pytest tests/test_dataset_rendering.py -v`

Expected: collection fails because the new modules and dataclasses are absent.

- [ ] **Step 3: Implement dataset dataclasses and loading**

Add to `annotate_tool/models.py`:

```python
@dataclass(frozen=True)
class ClassInfo:
    class_id: int
    name: str
    reference_path: Path | None


@dataclass(frozen=True)
class ImageRecord:
    path: Path
    relative_path: str
    label_path: Path
    parse_result: ParseResult
    image_size: tuple[int, int] | None
    image_error: str | None


@dataclass(frozen=True)
class AssignmentDataset:
    root: Path
    classes: tuple[ClassInfo, ...]
    images: tuple[ImageRecord, ...]
    class_metadata_path: Path
    problems: tuple[AnnotationProblem, ...]
```

Implement `load_assignment(root: Path) -> AssignmentDataset` and `filter_classes(classes, query)`. Enumerate supported images case-insensitively (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`), sort by relative POSIX path, map nested images to matching nested `.txt` paths, open images only long enough to validate and read dimensions, and aggregate problems without aborting healthy images.

- [ ] **Step 4: Implement rendering functions**

In `annotate_tool/rendering.py`, copy images before drawing. Use red 3-pixel outlines, yellow selected outlines, and filled high-contrast number badges. `crop_annotation` calls `box_pixels`, expands width/height by `padding_ratio`, clamps to the image, and rejects zero-area results. `reference_placeholder` returns a consistent `240x180` RGB card containing the ID and class name.

- [ ] **Step 5: Run dataset/rendering tests**

Run: `python -m pytest tests/test_dataset_rendering.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit the dataset/rendering increment**

```powershell
git add annotate_tool/models.py annotate_tool/dataset.py annotate_tool/rendering.py tests/conftest.py tests/test_dataset_rendering.py
git commit -m "feat: load and render annotation datasets"
```

---

### Task 5: Atomic Relabeling and Corrected-Label Export

**Files:**
- Create: `annotate_tool/storage.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: `replace_class_token` from Task 1, assignment roots from Task 2, and `ProgressRepository` from Task 3.
- Produces: `atomic_relabel(label_path, line_index, expected_line, new_class_id)`, `build_export(assignment_id, assignment_root, repository)`, and `ExportResult`.

- [ ] **Step 1: Write failing atomic-write and export tests**

Create `tests/test_storage.py` with:

```python
def test_atomic_relabel_preserves_all_coordinate_text(tmp_path):
    label = tmp_path / "a.txt"
    label.write_text("42 0.5220 0.433 0.13500 0.271\n", encoding="utf-8")
    atomic_relabel(label, 0, "42 0.5220 0.433 0.13500 0.271", 17)
    assert label.read_text(encoding="utf-8") == "17 0.5220 0.433 0.13500 0.271\n"


def test_atomic_relabel_rejects_stale_file_without_writing(tmp_path):
    label = tmp_path / "a.txt"
    label.write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed since it was loaded"):
        atomic_relabel(label, 0, "3 0.5 0.5 0.2 0.2", 4)
    assert label.read_text() == "2 0.5 0.5 0.2 0.2\n"


def test_export_contains_labels_metadata_progress_and_problems(imported_assignment, repository):
    result = build_export(imported_assignment.assignment_id, imported_assignment.root, repository)
    with ZipFile(BytesIO(result.content)) as archive:
        names = set(archive.namelist())
    assert "labels/a.txt" in names
    assert "progress.json" in names
    assert "problems.csv" in names
    assert not any(name.startswith("images/") or name.startswith("backups/") for name in names)
```

Patch `os.replace` to raise and verify the old label remains intact and temporary files are removed. Verify metadata is included for both YAML and text class mappings.

- [ ] **Step 2: Run storage tests and verify failure**

Run: `python -m pytest tests/test_storage.py -v`

Expected: collection fails because `annotate_tool.storage` does not exist.

- [ ] **Step 3: Implement atomic relabeling**

Implement the exact interface `atomic_relabel(label_path: Path, line_index: int, expected_line: str, new_class_id: int) -> None`.

Read UTF-8 text, call `replace_class_token`, create a named temporary file in `label_path.parent`, write with `newline=""`, flush, call `os.fsync`, copy the existing file mode where available, then `os.replace`. Remove the temporary file in `finally`. Never catch and hide stale-line or I/O errors.

- [ ] **Step 4: Implement in-memory ZIP export**

Create the frozen dataclass `ExportResult` with `filename: str` and `content: bytes`, plus the exact interface `build_export(assignment_id: str, assignment_root: Path, repository: ProgressRepository) -> ExportResult`.

Use `BytesIO` and `ZipFile`. Add all regular files under working `labels/`, the selected class metadata file, `progress.json` with repository summary/decisions, and `problems.csv` with `path,message` columns. Use POSIX archive paths and a filename derived from a safe assignment ID plus `_corrected_labels.zip`.

- [ ] **Step 5: Run storage tests**

Run: `python -m pytest tests/test_storage.py -v`

Expected: all tests pass.

- [ ] **Step 6: Commit the storage increment**

```powershell
git add annotate_tool/storage.py tests/test_storage.py
git commit -m "feat: save relabels atomically and export results"
```

---

### Task 6: Review Workflow and Crash-Safe Navigation

**Files:**
- Create: `annotate_tool/workflow.py`
- Create: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `AssignmentDataset`, `Annotation`, `ProgressRepository`, and `atomic_relabel`.
- Produces: `ObjectKey`, `ReviewCursor`, `flatten_objects`, `resume_cursor`, `move_cursor`, `record_correct`, `record_relabel`, and `record_skip`.

- [ ] **Step 1: Write failing workflow tests**

Create `tests/test_workflow.py` with:

```python
def test_resume_selects_first_unreviewed_valid_object(dataset, repository):
    objects = flatten_objects(dataset)
    repository.record_decision(dataset_id, objects[0].image_path, objects[0].line_index, "correct", 1, 1)
    cursor = resume_cursor(dataset_id, objects, repository)
    assert cursor.object_index == 1


def test_correct_persists_and_advances_without_touching_label(workflow_fixture):
    before = workflow_fixture.label_path.read_bytes()
    cursor = record_correct(**workflow_fixture.action_args)
    assert workflow_fixture.label_path.read_bytes() == before
    assert cursor.object_index == 1


def test_relabel_edits_expected_object_records_progress_and_advances(workflow_fixture):
    cursor = record_relabel(new_class_id=8, **workflow_fixture.action_args)
    assert workflow_fixture.label_path.read_text().splitlines()[0].startswith("8 ")
    assert workflow_fixture.repository.summary(workflow_fixture.dataset_id)["relabel"] == 1
    assert cursor.object_index == 1


def test_skip_advances_but_remains_available_on_next_resume(workflow_fixture):
    record_skip(**workflow_fixture.action_args)
    resumed = resume_cursor(workflow_fixture.dataset_id, workflow_fixture.objects, workflow_fixture.repository)
    assert resumed.object_index == 0
```

Also test crossing image boundaries, previous/next clamping, all-reviewed state, zero-object datasets, and stale edits not recording a decision.

- [ ] **Step 2: Run workflow tests and verify failure**

Run: `python -m pytest tests/test_workflow.py -v`

Expected: collection fails because `annotate_tool.workflow` does not exist.

- [ ] **Step 3: Implement object flattening and cursors**

Create:

```python
@dataclass(frozen=True)
class ObjectKey:
    image_index: int
    image_path: str
    label_path: Path
    line_index: int
    annotation: Annotation


@dataclass(frozen=True)
class ReviewCursor:
    object_index: int | None
    complete: bool


```

Add the exact interfaces `flatten_objects(dataset: AssignmentDataset) -> tuple[ObjectKey, ...]`, `resume_cursor(dataset_id: str, objects: tuple[ObjectKey, ...], repository: ProgressRepository) -> ReviewCursor`, and `move_cursor(cursor: ReviewCursor, objects: tuple[ObjectKey, ...], delta: int) -> ReviewCursor`.

Flatten valid annotations in image order and annotation line order. `resume_cursor` selects the first key absent from `reviewed_keys`; if every valid object is reviewed, return `ReviewCursor(None, True)`.

- [ ] **Step 4: Implement decisions with save-before-progress ordering**

Implement the exact interfaces `record_correct(dataset_id: str, objects: tuple[ObjectKey, ...], cursor: ReviewCursor, repository: ProgressRepository) -> ReviewCursor`, `record_relabel(dataset_id: str, objects: tuple[ObjectKey, ...], cursor: ReviewCursor, repository: ProgressRepository, new_class_id: int) -> ReviewCursor`, and `record_skip(dataset_id: str, objects: tuple[ObjectKey, ...], cursor: ReviewCursor, repository: ProgressRepository) -> ReviewCursor`. `record_relabel` uses `ObjectKey.label_path` and calls `atomic_relabel` before `record_decision`; all functions search forward from the current index for the next unreviewed object and wrap once. `skip` records a skip event and ignores the current key during that one forward search, while a later `resume_cursor` can return to it.

- [ ] **Step 5: Run workflow tests**

Run: `python -m pytest tests/test_workflow.py -v`

Expected: all tests pass.

- [ ] **Step 6: Run the complete non-UI suite**

Run: `python -m pytest tests/test_yolo.py tests/test_importer.py tests/test_progress.py tests/test_dataset_rendering.py tests/test_storage.py tests/test_workflow.py -v`

Expected: all tests pass.

- [ ] **Step 7: Commit the workflow increment**

```powershell
git add annotate_tool/workflow.py tests/test_workflow.py
git commit -m "feat: orchestrate durable annotation review"
```

---

### Task 7: Streamlit Web Interface

**Files:**
- Create: `app.py`
- Create: `.streamlit/config.toml`
- Create: `tests/test_app_smoke.py`

**Interfaces:**
- Consumes: all public interfaces from Tasks 2–6.
- Produces: browser-based import, assignment selection, review, search, navigation, progress, problem display, and export.

- [ ] **Step 1: Write a failing Streamlit smoke test**

Create `tests/test_app_smoke.py` using `streamlit.testing.v1.AppTest` and a temporary runtime root supplied through `ANNOTATE_TOOL_DATA_DIR`:

```python
def test_app_starts_and_shows_import_state(monkeypatch, tmp_path):
    monkeypatch.setenv("ANNOTATE_TOOL_DATA_DIR", str(tmp_path / "runtime"))
    app = AppTest.from_file("app.py").run(timeout=10)
    assert not app.exception
    assert app.title[0].value == "YOLO Class Review"
    assert any("Import an assignment" in item.value for item in app.info)
```

Add a seeded-assignment smoke test that checks the assignment selector, `Correct` button, crop image, progress metric, search input, and class-selection buttons render without exceptions.

- [ ] **Step 2: Run the smoke test and verify failure**

Run: `python -m pytest tests/test_app_smoke.py -v`

Expected: failure because `app.py` does not exist.

- [ ] **Step 3: Implement application initialization and import sidebar**

Create `.streamlit/config.toml`:

```toml
[server]
maxUploadSize = 4096
headless = true

[theme]
primaryColor = "#2563EB"
```

In `app.py`, call `st.set_page_config(page_title="YOLO Class Review", page_icon="🏷️", layout="wide")`. Resolve the runtime root from `ANNOTATE_TOOL_DATA_DIR`, defaulting to `./workspace`. Cache only immutable resources or repository construction with `st.cache_resource`; do not cache mutable label contents. Initialize SQLite, render an assignment-name field and ZIP uploader, save the uploaded bytes to staging, call `import_assignment`, register it, delete the temporary uploaded file, and show actionable errors without tracebacks.

- [ ] **Step 4: Implement assignment loading and session-state identity**

Use session-state keys `assignment_id`, `object_index`, `class_query`, and `flash_message`. When assignment selection changes, reload the dataset, record dataset problems, and call `resume_cursor`. Before every action, reconstruct the selected `ObjectKey` from the current dataset and cursor; never retain a mutable annotation object across reruns.

- [ ] **Step 5: Implement the two-column review page**

Render:

```text
Image X / Total    Object Y / Objects in image    Reviewed / Total    Percent
[Previous image] [Next image]                    [Previous object] [Next object]
```

The left column displays `draw_numbered_boxes` with a constrained width and one numbered button per valid object in the current image. The right column displays selected object number, current class ID/name, `crop_annotation`, a primary full-width `✅ Correct` button, and `Skip`. Empty/missing/malformed images show warnings plus image navigation instead of crashing.

- [ ] **Step 6: Implement searchable class cards and immediate actions**

Use `st.text_input("Search classes", key="class_query")`, `filter_classes`, and four Streamlit columns. Each card renders the reference image or `reference_placeholder`, class name, `ID: N`, and a button keyed by assignment/image/line/class IDs. Clicking calls `record_relabel` immediately and reruns. Correct, Skip, navigation, and object buttons update `object_index` and rerun. Do not add a per-object Save button.

- [ ] **Step 7: Implement problem reporting and export**

In the sidebar, render dataset and persisted problems in a collapsed expander. Build corrected-label export only when the download section is opened or a cached export is stale; pass its bytes to `st.download_button`. Add a visible notice that each assignment must be used by one annotator at a time and that machine-level backup protects against server-disk loss.

- [ ] **Step 8: Run Streamlit smoke tests**

Run: `python -m pytest tests/test_app_smoke.py -v`

Expected: all tests pass without Streamlit exceptions.

- [ ] **Step 9: Run the complete automated suite**

Run: `python -m pytest -v`

Expected: all tests pass.

- [ ] **Step 10: Commit the web interface increment**

```powershell
git add app.py .streamlit/config.toml tests/test_app_smoke.py
git commit -m "feat: add Streamlit annotation review interface"
```

---

### Task 8: Sample Dataset, Operations Documentation, and End-to-End Verification

**Files:**
- Create: `scripts/create_sample_data.py`
- Create: `README.md`
- Create: `.gitignore`
- Create at runtime only: `sample_data/sample_assignment.zip`

**Interfaces:**
- Consumes: the complete application.
- Produces: reproducible sample input, operator instructions, and final verification evidence.

- [ ] **Step 1: Write the deterministic sample generator**

Create `scripts/create_sample_data.py` using Pillow, `zipfile`, and fixed colors. It must generate:

- 89 class names and `references/0.jpg` through `references/88.jpg`;
- one image with two valid boxes;
- one image with an empty label file;
- one image with no label file;
- one image with a malformed label line;
- `sample_data/sample_assignment.zip` with stable internal paths.

Expose `create_sample_archive(output_path: Path) -> Path` and call it from `if __name__ == "__main__"`.

- [ ] **Step 2: Generate and validate the sample archive**

Run: `python scripts/create_sample_data.py`

Run: `python -c "from pathlib import Path; from annotate_tool.config import AppPaths, ImportLimits; from annotate_tool.importer import import_assignment; print(import_assignment(Path('sample_data/sample_assignment.zip'), 'Sample', AppPaths.from_root(Path('sample_data/runtime')), ImportLimits()).root)"`

Expected: the command prints an assignment path; the backup contains the original label files. Remove only the generated `sample_data/runtime` directory after the check, leaving the sample ZIP.

- [ ] **Step 3: Write setup and operations documentation**

Create `README.md` with exact sections:

1. Purpose and MVP limitations.
2. Required ZIP structure and 89-class/reference naming rules.
3. Windows setup using `py -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.txt`, and `.venv\Scripts\streamlit run app.py --server.address 0.0.0.0 --server.port 8501`.
4. Linux setup using `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, and `.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501`.
5. Persistent `ANNOTATE_TOOL_DATA_DIR` configuration.
6. One-assignment/one-annotator operating rule.
7. Immediate-save and restart behavior, including that an undecided object is not saved.
8. Corrected-label export and restore procedure.
9. Scheduled server backup recommendation.
10. Test and sample-data commands.
11. Troubleshooting for upload limits, invalid archives, malformed labels, and port/firewall access.

- [ ] **Step 4: Add generated/runtime exclusions**

Create `.gitignore`:

```text
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
workspace/
sample_data/runtime/
*.sqlite3
*.sqlite3-shm
*.sqlite3-wal
```

Keep `sample_data/sample_assignment.zip` tracked because it is the reproducible demonstration input.

- [ ] **Step 5: Run automated verification**

Run: `python -m pytest -v`

Expected: all tests pass.

Run: `python -m compileall -q app.py annotate_tool scripts`

Expected: exit code 0 with no output.

- [ ] **Step 6: Run the app and perform visual/behavioral verification**

Run: `streamlit run app.py --server.address 127.0.0.1 --server.port 8501`

Verify in a browser:

1. Import `sample_data/sample_assignment.zip` and select the resulting assignment.
2. Confirm the numbered overlay matches both boxes and each crop matches its selected box.
3. Search `Product 17`, select class 17, and confirm automatic advancement.
4. Press Correct on the next object and confirm automatic advancement.
5. Refresh the browser and restart Streamlit; confirm reviewed progress remains and the next unreviewed item resumes.
6. Confirm the working label changed only its class token and `backups/labels_original/` retained its original bytes.
7. Navigate through empty, missing, and malformed label cases without an exception.
8. Download the export and confirm it excludes images and backups.

- [ ] **Step 7: Review the final diff and status**

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only the intended Task 8 files are uncommitted.

- [ ] **Step 8: Commit the completed MVP**

```powershell
git add scripts/create_sample_data.py README.md .gitignore sample_data/sample_assignment.zip
git commit -m "docs: add sample data and deployment guide"
```

- [ ] **Step 9: Record final verification evidence**

Run: `git status --short`

Expected: no output.

Record in the delivery message: test count and result, compile check result, manual Streamlit checks completed, application start command, and the persistent workspace location requirement.
