# Project Based Annotation Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent project-based Streamlit annotation MVP with project-specific reference catalogs, arbitrary source class IDs, one-annotator ownership, and directly clickable bounding boxes.

**Architecture:** SQLite stores projects, ownership, progress, audit data, and reference metadata. Dataset files, immutable backups, and reference images remain in persistent server directories. An inline Streamlit components-v2 widget renders a responsive SVG box overlay without another frontend dependency.

**Tech Stack:** Python 3.11+, Streamlit 1.64 components v2, SQLite WAL, Pillow, PyYAML, standard-library ZIP/XML processing, pytest, Streamlit AppTest

**Spec:** `docs/superpowers/specs/2026-09-18-project-based-annotation-platform-design.md`

## Global Constraints

- Work directly on `main`; do not create a git worktree.
- Keep Python and Streamlit; do not add React, FastAPI, PostgreSQL, Redis, or object storage.
- Store structured records in SQLite and binaries in persistent server files.
- One annotator owns a project at a time; different projects may be edited concurrently.
- Only reference-catalog IDs may be written by relabeling.
- Accept any nonnegative source class ID and any source class count.
- Preserve all four coordinate tokens byte-for-byte during relabeling.
- Preserve existing IDs, paths, working labels, immutable backups, and progress during migration.
- Follow red-green-refactor TDD for every production change.

## File Map

Create:

- `annotate_tool/reference_catalog.py` for catalog validation, import, and loading.
- `annotate_tool/project_importer.py` for combined dataset/catalog import and rollback.
- `annotate_tool/clickable_boxes.py` for the components-v2 widget and click mapping.
- `scripts/create_reference_catalog.py` for deterministic DOCX-to-catalog conversion.
- `tests/test_reference_catalog.py`, `tests/test_project_importer.py`, and `tests/test_clickable_boxes.py`.

Modify:

- `annotate_tool/config.py`, `models.py`, `progress.py`, `dataset.py`, `yolo.py`, `storage.py`, `workflow.py`, and `importer.py`.
- `app.py`, `README.md`, sample generation, and the affected tests.

---

### Task 1: Versioned Project Schema and Ownership

**Files:** Modify `annotate_tool/config.py`, `annotate_tool/progress.py`, and `tests/test_progress.py`.

**Produces:** `AppPaths.projects`; `ProjectRecord`; `register_project`, `assign_project`, `get_project`, `list_projects`, and `can_edit_project`; annotator name on new decisions. Preserve assignment APIs as temporary wrappers.

- [ ] **Step 1: Write failing migration and ownership tests**

```python
def test_initialize_migrates_legacy_assignment_without_losing_progress(tmp_path):
    repository = create_legacy_repository_with_one_decision(tmp_path)
    repository.initialize()
    project = repository.get_project("assignment-1")
    assert project.dataset_root.name == "assignment-1"
    assert project.reference_root is None
    assert repository.summary("assignment-1")["reviewed"] == 1

def test_project_owner_controls_edit_access(tmp_path):
    repository = initialized_repository(tmp_path)
    repository.register_project("p1", "Hair 001", tmp_path / "dataset", tmp_path / "references")
    repository.assign_project("p1", "Alice")
    assert repository.can_edit_project("p1", "Alice")
    assert not repository.can_edit_project("p1", "Bob")
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_progress.py -q`. Expect missing project APIs.

- [ ] **Step 3: Implement the idempotent migration**

Add `projects/` to `AppPaths`. Add a `schema_version` table; add `dataset_root`, `reference_root`, and `owner_name` columns only when absent; copy legacy `root` into `dataset_root`; add nullable `annotator_name` to decisions. Create:

```sql
CREATE TABLE IF NOT EXISTS reference_classes (
  assignment_id TEXT NOT NULL,
  class_id INTEGER NOT NULL CHECK (class_id >= 0),
  display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
  image_path TEXT NOT NULL,
  display_order INTEGER NOT NULL CHECK (display_order >= 0),
  PRIMARY KEY (assignment_id, class_id),
  FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
);
```

Reject blank owner names. `can_edit_project` returns true only for the exact stored owner.

- [ ] **Step 4: Verify GREEN and commit**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_progress.py tests\test_storage.py tests\test_workflow.py -q`.

Commit: `git commit -m "feat: add project ownership schema"` with the modified files and tests.

---

### Task 2: Arbitrary Source IDs and Explicit Target IDs

**Files:** Modify `models.py`, `dataset.py`, `yolo.py`, `storage.py`, `workflow.py`, and their existing tests.

**Produces:** `AssignmentDataset.source_class_names`; `source_class_name(dataset, id)`; `parse_label_text(text, expected_classes=None)`; write APIs accepting `allowed_class_ids: Collection[int]`.

- [ ] **Step 1: Write failing source/target tests**

```python
def test_parser_accepts_any_nonnegative_source_class():
    parsed = parse_label_text("9402 0.5 0.5 0.2 0.2\n")
    assert parsed.annotations[0].class_id == 9402
    assert parsed.problems == ()

def test_sparse_metadata_and_unmapped_source_do_not_block_loading(dataset_root):
    write_yaml_names(dataset_root, {2: "Legacy two", 9402: "Legacy special"})
    write_label(dataset_root, "9999 0.5 0.5 0.2 0.2\n")
    dataset = load_assignment(dataset_root, reference_classes=())
    assert source_class_name(dataset, 9999) == "Unknown source class 9999"

def test_relabel_rejects_id_absent_from_reference_catalog(tmp_path):
    label = write_label_file(tmp_path, "9999 0.5 0.5 0.2 0.2\n")
    with pytest.raises(ValueError, match="reference catalog"):
        atomic_relabel(label, 0, "9999 0.5 0.5 0.2 0.2", 4, {1, 7, 20})
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_yolo.py tests\test_dataset_rendering.py tests\test_storage.py -q`.

- [ ] **Step 3: Implement source/target separation**

Normalize YAML lists, sparse numeric dictionaries, and `classes.txt` into `dict[int, str]`. Missing metadata yields `{}`. Reject negative keys and blank names, but never require a fixed count. Unbounded parsing rejects only negative or noninteger class tokens. Write validation becomes:

```python
allowed_ids = frozenset(allowed_class_ids)
if new_class_id not in allowed_ids:
    raise ValueError(f"class ID {new_class_id} is not in the project reference catalog")
```

Thread allowed IDs through workflow and storage while preserving expected-line checks and coordinate strings.

- [ ] **Step 4: Verify GREEN and commit**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_yolo.py tests\test_dataset_rendering.py tests\test_storage.py tests\test_workflow.py -q`.

Commit: `git commit -m "feat: decouple source and target classes"`.

---

### Task 3: Reference Catalogs and DOCX Conversion

**Files:** Create `annotate_tool/reference_catalog.py`, `scripts/create_reference_catalog.py`, `tests/test_reference_catalog.py`; modify `models.py`, `progress.py`, and `dataset.py`.

**Produces:** `ReferenceClass`; `inspect_catalog_zip`; `import_reference_catalog`; `load_reference_catalog`; CLI `create_reference_catalog.py INPUT.docx OUTPUT.zip`.

- [ ] **Step 1: Write failing catalog tests**

```python
def test_imports_sparse_ids_as_only_target_classes(tmp_path):
    archive = make_catalog_zip(tmp_path, {1: ("Blue", png_bytes()), 7: ("Green", png_bytes())})
    classes = import_reference_catalog(archive, tmp_path / "references", ImportLimits())
    assert [(item.class_id, item.name) for item in classes] == [(1, "Blue"), (7, "Green")]

@pytest.mark.parametrize("problem", ["missing_image", "duplicate_id", "bad_stem", "unreadable_image"])
def test_invalid_catalog_leaves_no_destination(tmp_path, problem):
    destination = tmp_path / "references"
    with pytest.raises(ReferenceCatalogError):
        import_reference_catalog(invalid_catalog_zip(tmp_path, problem), destination, ImportLimits())
    assert not destination.exists()

def test_docx_converter_maps_table_cells_row_major(tmp_path):
    source = build_catalog_docx(tmp_path, count=89)
    output = tmp_path / "catalog.zip"
    assert main([str(source), str(output)]) == 0
    assert catalog_ids(output) == list(range(89))
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_reference_catalog.py -q`.

- [ ] **Step 3: Implement safe catalog ZIP import**

Require `catalog.yaml` numeric names plus `references/<id>.<supported_extension>`. Reuse archive safety limits. Validate every image with Pillow, copy without populated-directory renames, write `.catalog_complete` last, and remove only the exact incomplete destination on failure.

- [ ] **Step 4: Implement DOCX conversion without a runtime dependency**

Use `zipfile` and `xml.etree.ElementTree` to read `word/document.xml` and its relationships. For each populated table cell in document order, require one `a:blip` and a nonblank concatenation of `w:t` text. Assign sequential IDs from zero and write deterministic `catalog.yaml` plus numeric reference files.

- [ ] **Step 5: Persist and load catalog metadata**

Add transactional repository replace/list methods. `load_assignment(dataset_root, reference_classes)` uses only supplied reference classes as `dataset.classes`; source names remain separate.

- [ ] **Step 6: Verify GREEN and commit**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_reference_catalog.py tests\test_dataset_rendering.py tests\test_progress.py -q`.

Commit: `git commit -m "feat: add project reference catalogs"`.

---

### Task 4: Atomic Project Import

**Files:** Create `annotate_tool/project_importer.py`, `tests/test_project_importer.py`; modify `importer.py` and `tests/test_importer.py`.

**Produces:** `ImportedProject`; `import_project(dataset_zip, catalog_zip, display_name, owner_name, paths, limits)`.

- [ ] **Step 1: Write failing combined-import tests**

```python
def test_import_project_publishes_dataset_and_catalog_together(tmp_path):
    imported = import_project(dataset_zip(tmp_path), catalog_zip(tmp_path), "Hair 001", "Alice", paths(tmp_path), limits())
    assert imported.dataset_root.name == "dataset"
    assert imported.reference_root.name == "references"
    assert [item.class_id for item in imported.reference_classes] == [1, 7]

def test_catalog_failure_rolls_back_unregistered_project(tmp_path):
    app_paths = paths(tmp_path)
    with pytest.raises(ProjectImportError):
        import_project(dataset_zip(tmp_path), broken_catalog_zip(tmp_path), "Bad", "Alice", app_paths, limits())
    assert list(app_paths.projects.iterdir()) == []
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_project_importer.py -q`.

- [ ] **Step 3: Implement orchestration**

Refactor dataset extraction to accept a caller-provided empty destination while preserving its wrapper API and safety tests. Create a UUID project directory, import into `dataset/` and `references/`, and return only after both completion markers exist. On failure, remove only that resolved project directory. Register SQLite records only after file import returns.

- [ ] **Step 4: Verify GREEN and commit**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_importer.py tests\test_project_importer.py -q`, including Windows directory-rename denial.

Commit: `git commit -m "feat: import persistent annotation projects"`.

---

### Task 5: Clickable Bounding Boxes

**Files:** Create `annotate_tool/clickable_boxes.py`, `tests/test_clickable_boxes.py`; modify rendering tests.

**Produces:** `build_clickable_image_payload`; `clicked_object_index`; module-level `clickable_box_image` components-v2 renderer.

- [ ] **Step 1: Write failing geometry tests**

```python
def test_payload_uses_original_pixel_space_and_line_ids():
    payload = build_clickable_image_payload(image_100_by_80(), annotations(), selected_line_index=4)
    assert payload["width"] == 100
    assert payload["height"] == 80
    assert payload["boxes"][0] == {"line_index": 4, "number": 1, "x": 40, "y": 32, "width": 20, "height": 16, "selected": True}

def test_clicked_line_selects_object_on_current_image():
    assert clicked_object_index(objects_fixture(), image_index=2, line_index=7) == 5
    assert clicked_object_index(objects_fixture(), image_index=2, line_index=99) is None
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_clickable_boxes.py -q`.

- [ ] **Step 3: Build the component**

Encode the rendered Pillow image as PNG base64. Send pixel-space boxes using existing `box_pixels`. JavaScript creates the image and SVG nodes from `component.data`, uses an original-size `viewBox`, and reports clicks:

```javascript
rectangle.onclick = (event) => {
  event.stopPropagation();
  setTriggerValue("selected", box.line_index);
};
```

Use transparent clickable fills, hover feedback, and a stronger selected stroke. Never interpolate dataset text into trusted HTML or JavaScript source.

- [ ] **Step 4: Verify GREEN and commit**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_clickable_boxes.py tests\test_dataset_rendering.py -q`.

Commit: `git commit -m "feat: select annotations from image boxes"`.

---

### Task 6: Project UI and Enforcement

**Files:** Modify `app.py`, `workflow.py`, `storage.py`, `tests/test_app_smoke.py`, `tests/test_workflow.py`, and `tests/test_storage.py`.

**Consumes:** All APIs from Tasks 1-5.

- [ ] **Step 1: Write failing UI and authorization tests**

```python
def test_owned_project_has_no_object_buttons(app_with_owned_project):
    app = app_with_owned_project("Alice")
    assert not any(button.label.startswith("Object ") for button in app.button)

def test_correct_is_disabled_when_source_id_is_not_a_target(app_with_unknown_source):
    correct = next(button for button in app_with_unknown_source.button if button.label == "✅ Correct")
    assert correct.disabled

def test_non_owner_cannot_relabel(project_fixture):
    with pytest.raises(PermissionError, match="assigned to Alice"):
        record_relabel(annotator_name="Bob", new_class_id=7, **project_fixture)
```

- [ ] **Step 2: Verify RED**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_app_smoke.py tests\test_workflow.py -q`.

- [ ] **Step 3: Implement project selection and admin import**

Add annotator and project selectors. Show owned projects as editable and ownership status for others. Add one-time admin fields for project name, owner, dataset ZIP, and catalog ZIP. Register project/reference rows only after combined import succeeds.

- [ ] **Step 4: Replace object buttons with click handling**

Mount the component for the current image. Resolve `result.selected` with `clicked_object_index`, update cursor state, and rerun. Remove the object-button grid; preserve previous/next controls.

- [ ] **Step 5: Enforce targets and ownership**

Use `source_class_name` for current labels. Disable Correct unless the current ID is in the reference ID set. Pass that set into relabel actions. Check ownership inside workflow actions, not only in UI rendering.

- [ ] **Step 6: Update export and verify GREEN**

Export corrected labels, source metadata if present, catalog metadata, annotator-aware progress, and problems; exclude images, reference binaries, and backups.

Run `.\.venv\Scripts\python.exe -m pytest tests\test_app_smoke.py tests\test_workflow.py tests\test_storage.py -q`.

Commit: `git commit -m "feat: add persistent project annotation UI"`.

---

### Task 7: Hair Catalog Migration and Full Verification

**Files:** Modify `README.md`, `scripts/create_sample_data.py`, `tests/test_sample_data.py`; update ignored runtime workspace data only for the existing hair project.

- [ ] **Step 1: Write a failing sample integration test**

```python
def test_sample_project_uses_sparse_catalog_and_arbitrary_source_id(sample_project):
    dataset = load_sample_project(sample_project)
    assert [item.class_id for item in dataset.classes] == [1, 7, 20]
    assert all(item.reference_path.is_file() for item in dataset.classes)
    assert source_class_name(dataset, 9999) == "Unknown source class 9999"
```

- [ ] **Step 2: Verify RED, update sample generation, and document operations**

Run `.\.venv\Scripts\python.exe -m pytest tests\test_sample_data.py -q`. Then generate separate sample dataset/catalog ZIPs and document admin import, catalogs, ownership, persistence, backup, export, and deployment.

- [ ] **Step 3: Convert the supplied catalog**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\create_reference_catalog.py 'C:\Users\First\Downloads\HAIR_SKU_product_images.docx' '.\workspace\hair_reference_catalog.zip'
```

Assert the ZIP contains 89 IDs, 89 readable images, and nonblank names.

- [ ] **Step 4: Attach it to the existing project safely**

Import into `workspace/assignments/470c0e26f17245adadee5c8122b7f11c/references`, register rows transactionally, and leave labels, backup files, and progress untouched. Before any cleanup, resolve and verify each target remains under `C:\Users\First\OneDrive\Desktop\annotate_tool\workspace`.

- [ ] **Step 5: Run full verification**

Run `.\.venv\Scripts\python.exe -m pytest -q --basetemp='.\workspace\pytest-project-platform'` and `.\.venv\Scripts\python.exe -m compileall -q annotate_tool scripts tests app.py`.

Validate the real project has 89 targets, 632 images, 41,961 annotations, 28,501 source-ID-89 annotations, zero parsing problems, unchanged backup hashes, and unchanged prior progress.

- [ ] **Step 6: Browser verification**

Start Streamlit on a test port. Click small, medium, and overlapping boxes and confirm the correct crop/highlight at desktop and narrow widths. Confirm there are no Object buttons, a reference card changes only the class token, and refresh resumes progress.

- [ ] **Step 7: Final repository checks and commit**

Run `git diff --check` and `git status --short`. Commit documentation, sample, and test changes as `docs: finish project annotation MVP`.

## Completion Gate

After the final commit, rerun the full suite and real-project validation. Confirm the current project opens without re-import, its original backup and existing progress are unchanged, every written ID comes from its reference catalog, direct box clicks work at two viewport widths, and the tracked worktree is clean.
