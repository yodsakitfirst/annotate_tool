import os
from pathlib import Path
import tempfile

from PIL import Image
import streamlit as st

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.clickable_boxes import (
    build_clickable_image_payload,
    clickable_box_image,
    clicked_object_index,
)
from annotate_tool.dataset import (
    DatasetLoadError,
    filter_classes,
    load_assignment,
    source_class_name,
)
from annotate_tool.project_importer import ProjectImportError, import_project
from annotate_tool.progress import ProgressRepository
from annotate_tool.rendering import crop_annotation, reference_placeholder
from annotate_tool.storage import build_export
from annotate_tool.workflow import (
    ReviewCursor,
    flatten_objects,
    move_cursor,
    record_correct,
    record_relabel,
    record_skip,
    resume_cursor,
)


st.set_page_config(page_title="YOLO Class Review", page_icon="🏷️", layout="wide")


def runtime_paths() -> AppPaths:
    root = Path(os.environ.get("ANNOTATE_TOOL_DATA_DIR", "workspace"))
    paths = AppPaths.from_root(root)
    paths.ensure()
    return paths


def project_labels(projects):
    name_counts: dict[str, int] = {}
    for item in projects:
        name_counts[item.display_name] = name_counts.get(item.display_name, 0) + 1
    return {
        (
            f"{item.display_name} · {item.owner_name or 'Unassigned'}"
            if name_counts[item.display_name] == 1
            else f"{item.display_name} · {item.owner_name or 'Unassigned'} · {item.project_id[:8]}"
        ): item
        for item in projects
    }


def set_cursor(cursor: ReviewCursor, objects) -> None:
    st.session_state.object_index = cursor.object_index
    st.session_state.review_complete = cursor.complete
    if cursor.object_index is not None:
        st.session_state.view_image_index = objects[cursor.object_index].image_index


def choose_image(image_index: int, objects) -> None:
    st.session_state.view_image_index = image_index
    st.session_state.review_complete = False
    st.session_state.object_index = next(
        (index for index, item in enumerate(objects) if item.image_index == image_index),
        None,
    )


paths = runtime_paths()
repository = ProgressRepository(paths.database)
repository.initialize()

st.title("YOLO Class Review")
st.caption("Fast, lossless class review for existing YOLO bounding boxes")

with st.sidebar:
    st.header("Projects")
    annotator_name = st.text_input("Annotator name", key="annotator_name").strip()
    with st.expander("Import project", expanded=not repository.list_projects()):
        import_name = st.text_input("Project name", key="import_name")
        import_owner = st.text_input("Assigned annotator", key="import_owner")
        dataset_upload = st.file_uploader("Dataset ZIP", type=("zip",), key="dataset_zip")
        catalog_upload = st.file_uploader(
            "Reference catalog ZIP", type=("zip",), key="catalog_zip"
        )
        if st.button("Import project", type="primary", width="stretch"):
            if dataset_upload is None or catalog_upload is None:
                st.error("Choose both the dataset ZIP and reference catalog ZIP.")
            else:
                dataset_temporary: Path | None = None
                catalog_temporary: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=paths.staging,
                        prefix="dataset_",
                        suffix=".zip",
                        delete=False,
                    ) as temporary:
                        temporary.write(dataset_upload.getbuffer())
                        dataset_temporary = Path(temporary.name)
                    with tempfile.NamedTemporaryFile(
                        dir=paths.staging,
                        prefix="catalog_",
                        suffix=".zip",
                        delete=False,
                    ) as temporary:
                        temporary.write(catalog_upload.getbuffer())
                        catalog_temporary = Path(temporary.name)
                    imported = import_project(
                        dataset_temporary,
                        catalog_temporary,
                        import_name,
                        import_owner,
                        paths,
                        ImportLimits(),
                    )
                    repository.register_project(
                        imported.project_id,
                        imported.display_name,
                        imported.dataset_root,
                        imported.reference_root,
                        imported.owner_name,
                    )
                    repository.replace_reference_classes(
                        imported.project_id, imported.reference_classes
                    )
                    st.session_state.project_id = imported.project_id
                    st.success(f"Imported {imported.display_name}.")
                    st.rerun()
                except (ProjectImportError, ValueError) as exc:
                    st.error(str(exc))
                finally:
                    if dataset_temporary is not None:
                        dataset_temporary.unlink(missing_ok=True)
                    if catalog_temporary is not None:
                        catalog_temporary.unlink(missing_ok=True)

    projects = repository.list_projects()
    if projects:
        labels = project_labels(projects)
        current_id = st.session_state.get("project_id")
        default_index = next(
            (index for index, item in enumerate(labels.values()) if item.project_id == current_id),
            0,
        )
        selected_label = st.selectbox("Project", tuple(labels), index=default_index, key="project_id_label")
        selected_project = labels[selected_label]
        st.session_state.project_id = selected_project.project_id
    else:
        selected_project = None

    st.caption("Each project has one assigned annotator. Decisions save immediately.")

if selected_project is None:
    st.info("Import a project in the sidebar to begin.")
    st.stop()
if not annotator_name:
    st.info("Enter your annotator name in the sidebar to open a project.")
    st.stop()

editable = repository.can_edit_project(selected_project.project_id, annotator_name)
if not editable:
    st.warning(f"This project is assigned to {selected_project.owner_name or 'no annotator'} and is read-only for {annotator_name}.")

try:
    reference_classes = repository.list_reference_classes(selected_project.project_id)
    if not reference_classes:
        raise DatasetLoadError("project has no valid reference catalog")
    dataset = load_assignment(selected_project.dataset_root, reference_classes=reference_classes)
except (DatasetLoadError, ValueError) as exc:
    st.error(f"Cannot open this project: {exc}")
    st.stop()

for problem in dataset.problems:
    if problem.path is None:
        problem_path = "dataset"
    else:
        try:
            problem_path = problem.path.relative_to(dataset.root).as_posix()
        except ValueError:
            problem_path = str(problem.path)
    repository.record_problem(selected_project.project_id, problem_path, problem.message)

objects = flatten_objects(dataset)
context_changed = st.session_state.get("loaded_project_id") != selected_project.project_id
if context_changed:
    initial_cursor = resume_cursor(selected_project.project_id, objects, repository)
    st.session_state.loaded_project_id = selected_project.project_id
    st.session_state.view_image_index = objects[0].image_index if objects else 0
    set_cursor(initial_cursor, objects)

if "view_image_index" not in st.session_state:
    st.session_state.view_image_index = 0
if "object_index" not in st.session_state:
    set_cursor(resume_cursor(selected_project.project_id, objects, repository), objects)
if "review_complete" not in st.session_state:
    st.session_state.review_complete = False

view_image_index = max(0, min(len(dataset.images) - 1, st.session_state.view_image_index)) if dataset.images else 0
st.session_state.view_image_index = view_image_index
object_index = st.session_state.object_index
if object_index is not None and not 0 <= object_index < len(objects):
    object_index = None
    st.session_state.object_index = None

summary = repository.summary(selected_project.project_id)
reviewed = summary["reviewed"]
total_objects = len(objects)
metrics = st.columns(4)
metrics[0].metric("Image", f"{view_image_index + 1 if dataset.images else 0} / {len(dataset.images)}")
image_objects = [
    (index, item) for index, item in enumerate(objects) if item.image_index == view_image_index
]
selected_position = next(
    (position for position, (index, _) in enumerate(image_objects, start=1) if index == object_index),
    0,
)
metrics[1].metric("Object", f"{selected_position} / {len(image_objects)}")
metrics[2].metric("Reviewed", f"{reviewed} / {total_objects}")
percent = int((reviewed / total_objects) * 100) if total_objects else 100
metrics[3].metric("Complete", f"{percent}%")
st.progress(percent / 100)

navigation = st.columns(4)
if navigation[0].button("← Previous image", disabled=view_image_index <= 0, width="stretch"):
    choose_image(view_image_index - 1, objects)
    st.rerun()
if navigation[1].button(
    "Next image →",
    disabled=not dataset.images or view_image_index >= len(dataset.images) - 1,
    width="stretch",
):
    choose_image(view_image_index + 1, objects)
    st.rerun()
if navigation[2].button("← Previous object", disabled=object_index is None or object_index <= 0, width="stretch"):
    set_cursor(move_cursor(ReviewCursor(object_index, False), objects, -1), objects)
    st.rerun()
if navigation[3].button(
    "Next object →",
    disabled=object_index is None or object_index >= len(objects) - 1,
    width="stretch",
):
    set_cursor(move_cursor(ReviewCursor(object_index, False), objects, 1), objects)
    st.rerun()

if st.session_state.review_complete and total_objects:
    st.success("Assignment complete — every valid object has been reviewed.")

left, right = st.columns((1.15, 1), gap="large")

with left:
    st.subheader("Original image")
    if not dataset.images:
        st.warning("This assignment contains no supported images.")
    else:
        image_record = dataset.images[view_image_index]
        if image_record.image_error:
            st.error(image_record.image_error)
        else:
            with Image.open(image_record.path) as source_image:
                source_image.load()
                selected_line_index = (
                    objects[object_index].line_index
                    if object_index is not None
                    and objects[object_index].image_index == view_image_index
                    else None
                )
                payload = build_clickable_image_payload(
                    source_image,
                    image_record.parse_result.annotations,
                    selected_line_index,
                )
                click_result = clickable_box_image(
                    data=payload,
                    key=f"boxes_{selected_project.project_id}_{view_image_index}",
                    on_selected_change=lambda: None,
                )
                clicked_line = getattr(click_result, "selected", None)
                if clicked_line is not None:
                    clicked_index = clicked_object_index(
                        objects, view_image_index, int(clicked_line)
                    )
                    if clicked_index is not None and clicked_index != object_index:
                        st.session_state.object_index = clicked_index
                        st.session_state.review_complete = False
                        st.rerun()

        if image_record.parse_result.problems:
            st.error("This label file is malformed and is read-only. See Problems for details.")
        elif not image_objects:
            st.info("This image has no valid annotations.")

with right:
    st.subheader("Selected object")
    selected = objects[object_index] if object_index is not None else None
    if selected is None or selected.image_index != view_image_index:
        st.info("Select an object on this image to review it.")
    else:
        st.markdown(f"### Object #{selected_position}")
        st.markdown(
            f"**Current:** Class {selected.annotation.class_id} — "
            f"{source_class_name(dataset, selected.annotation.class_id)}"
        )
        with Image.open(dataset.images[selected.image_index].path) as source_image:
            source_image.load()
            st.image(crop_annotation(source_image, selected.annotation), width="stretch")

        action_columns = st.columns((2, 1))
        target_ids = frozenset(item.class_id for item in dataset.classes)
        needs_relabel = selected.annotation.class_id not in target_ids
        if action_columns[0].button(
            "✅ Correct",
            type="primary",
            width="stretch",
            disabled=needs_relabel or not editable,
        ):
            next_cursor = record_correct(
                selected_project.project_id,
                objects,
                ReviewCursor(object_index, False),
                repository,
                annotator_name=annotator_name,
                allowed_class_ids=target_ids,
            )
            set_cursor(next_cursor, objects)
            st.rerun()
        if needs_relabel:
            st.caption("This source class must be changed to a project reference class.")
        if action_columns[1].button("Skip", width="stretch", disabled=not editable):
            next_cursor = record_skip(
                selected_project.project_id,
                objects,
                ReviewCursor(object_index, False),
                repository,
                annotator_name=annotator_name,
            )
            set_cursor(next_cursor, objects)
            st.rerun()

        st.divider()
        st.markdown("### Choose another class")
        class_query = st.text_input("Search classes", key="class_query", placeholder="Name or class ID")
        filtered = filter_classes(dataset.classes, class_query)
        if not filtered:
            st.info("No classes match this search.")
        else:
            card_columns = st.columns(4)
            for card_index, candidate in enumerate(filtered):
                with card_columns[card_index % 4]:
                    if candidate.reference_path is not None:
                        st.image(str(candidate.reference_path), width="stretch")
                    else:
                        st.image(reference_placeholder(candidate), width="stretch")
                    st.markdown(f"**{candidate.name}**  \nID: {candidate.class_id}")
                    if st.button(
                        f"Select class {candidate.class_id}",
                        key=(
                            f"class_{selected_project.project_id}_"
                            f"{selected.image_path}_{selected.line_index}_{candidate.class_id}"
                        ),
                        width="stretch",
                        disabled=not editable,
                    ):
                        try:
                            next_cursor = record_relabel(
                                selected_project.project_id,
                                objects,
                                ReviewCursor(object_index, False),
                                repository,
                                candidate.class_id,
                                allowed_class_ids=target_ids,
                                annotator_name=annotator_name,
                            )
                        except (OSError, PermissionError, ValueError) as exc:
                            st.error(f"Could not save this change: {exc}")
                        else:
                            set_cursor(next_cursor, objects)
                            st.rerun()

with st.sidebar:
    problems = repository.list_problems(selected_project.project_id)
    with st.expander(f"Problems ({len(problems)})"):
        if not problems:
            st.caption("No dataset problems found.")
        for problem_path, message in problems:
            st.markdown(f"- `{problem_path}` — {message}")

    with st.expander("Export corrected labels"):
        export = build_export(
            selected_project.project_id,
            dataset.root,
            repository,
            reference_classes=dataset.classes,
        )
        st.download_button(
            "Download results ZIP",
            data=export.content,
            file_name=export.filename,
            mime="application/zip",
            width="stretch",
        )
