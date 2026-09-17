import os
from pathlib import Path
import tempfile

from PIL import Image
import streamlit as st

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.dataset import DatasetLoadError, filter_classes, load_assignment
from annotate_tool.importer import AssignmentImportError, import_assignment
from annotate_tool.progress import ProgressRepository
from annotate_tool.rendering import crop_annotation, draw_numbered_boxes, reference_placeholder
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


def assignment_labels(assignments):
    name_counts: dict[str, int] = {}
    for item in assignments:
        name_counts[item.display_name] = name_counts.get(item.display_name, 0) + 1
    return {
        (
            item.display_name
            if name_counts[item.display_name] == 1
            else f"{item.display_name} · {item.assignment_id[:8]}"
        ): item
        for item in assignments
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
    st.header("Assignments")
    with st.expander("Import ZIP", expanded=not repository.list_assignments()):
        import_name = st.text_input("Assignment name", key="import_name")
        uploaded = st.file_uploader("Dataset ZIP", type=("zip",), key="dataset_zip")
        if st.button("Import assignment", type="primary", width="stretch"):
            if uploaded is None:
                st.error("Choose a ZIP file first.")
            else:
                temporary_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=paths.staging,
                        prefix="upload_",
                        suffix=".zip",
                        delete=False,
                    ) as temporary:
                        temporary.write(uploaded.getbuffer())
                        temporary_path = Path(temporary.name)
                    imported = import_assignment(
                        temporary_path,
                        import_name,
                        paths,
                        ImportLimits(),
                    )
                    repository.register_assignment(
                        imported.assignment_id,
                        imported.display_name,
                        imported.root,
                    )
                    st.session_state.assignment_id = imported.assignment_id
                    st.success(f"Imported {imported.display_name}.")
                    st.rerun()
                except AssignmentImportError as exc:
                    st.error(str(exc))
                finally:
                    if temporary_path is not None:
                        temporary_path.unlink(missing_ok=True)

    assignments = repository.list_assignments()
    if assignments:
        labels = assignment_labels(assignments)
        current_id = st.session_state.get("assignment_id")
        default_index = next(
            (index for index, item in enumerate(labels.values()) if item.assignment_id == current_id),
            0,
        )
        selected_label = st.selectbox("Assigned dataset", tuple(labels), index=default_index)
        selected_assignment = labels[selected_label]
        st.session_state.assignment_id = selected_assignment.assignment_id
    else:
        selected_assignment = None

    st.warning("Use each assignment with one annotator at a time.")
    st.caption("Completed decisions are saved immediately. Back up the server workspace to protect against disk loss.")

if selected_assignment is None:
    st.info("Import an assignment ZIP in the sidebar to begin.")
    st.stop()

try:
    dataset = load_assignment(selected_assignment.root)
except DatasetLoadError as exc:
    st.error(f"Cannot open this assignment: {exc}")
    st.stop()

for problem in dataset.problems:
    if problem.path is None:
        problem_path = "dataset"
    else:
        try:
            problem_path = problem.path.relative_to(dataset.root).as_posix()
        except ValueError:
            problem_path = str(problem.path)
    repository.record_problem(selected_assignment.assignment_id, problem_path, problem.message)

objects = flatten_objects(dataset)
context_changed = st.session_state.get("loaded_assignment_id") != selected_assignment.assignment_id
if context_changed:
    initial_cursor = resume_cursor(selected_assignment.assignment_id, objects, repository)
    st.session_state.loaded_assignment_id = selected_assignment.assignment_id
    st.session_state.view_image_index = objects[0].image_index if objects else 0
    set_cursor(initial_cursor, objects)

if "view_image_index" not in st.session_state:
    st.session_state.view_image_index = 0
if "object_index" not in st.session_state:
    set_cursor(resume_cursor(selected_assignment.assignment_id, objects, repository), objects)
if "review_complete" not in st.session_state:
    st.session_state.review_complete = False

view_image_index = max(0, min(len(dataset.images) - 1, st.session_state.view_image_index)) if dataset.images else 0
st.session_state.view_image_index = view_image_index
object_index = st.session_state.object_index
if object_index is not None and not 0 <= object_index < len(objects):
    object_index = None
    st.session_state.object_index = None

summary = repository.summary(selected_assignment.assignment_id)
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
                selected_local_index = next(
                    (
                        local_index
                        for local_index, annotation in enumerate(image_record.parse_result.annotations)
                        if object_index is not None
                        and annotation.line_index == objects[object_index].line_index
                        and objects[object_index].image_index == view_image_index
                    ),
                    None,
                )
                rendered = draw_numbered_boxes(
                    source_image,
                    image_record.parse_result.annotations,
                    selected_local_index,
                )
                st.image(rendered, width="stretch")

        if image_record.parse_result.problems:
            st.error("This label file is malformed and is read-only. See Problems for details.")
        elif not image_objects:
            st.info("This image has no valid annotations.")
        else:
            button_columns = st.columns(min(6, len(image_objects)))
            for position, (global_index, _) in enumerate(image_objects):
                if button_columns[position % len(button_columns)].button(
                    f"Object {position + 1}",
                    key=f"object_{selected_assignment.assignment_id}_{global_index}",
                    type="primary" if global_index == object_index else "secondary",
                    width="stretch",
                ):
                    st.session_state.object_index = global_index
                    st.session_state.review_complete = False
                    st.rerun()

with right:
    st.subheader("Selected object")
    selected = objects[object_index] if object_index is not None else None
    if selected is None or selected.image_index != view_image_index:
        st.info("Select an object on this image to review it.")
    else:
        class_info = dataset.classes[selected.annotation.class_id]
        st.markdown(f"### Object #{selected_position}")
        st.markdown(f"**Current:** Class {class_info.class_id} — {class_info.name}")
        with Image.open(dataset.images[selected.image_index].path) as source_image:
            source_image.load()
            st.image(crop_annotation(source_image, selected.annotation), width="stretch")

        action_columns = st.columns((2, 1))
        if action_columns[0].button("✅ Correct", type="primary", width="stretch"):
            next_cursor = record_correct(
                selected_assignment.assignment_id,
                objects,
                ReviewCursor(object_index, False),
                repository,
            )
            set_cursor(next_cursor, objects)
            st.rerun()
        if action_columns[1].button("Skip", width="stretch"):
            next_cursor = record_skip(
                selected_assignment.assignment_id,
                objects,
                ReviewCursor(object_index, False),
                repository,
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
                            f"class_{selected_assignment.assignment_id}_"
                            f"{selected.image_path}_{selected.line_index}_{candidate.class_id}"
                        ),
                        width="stretch",
                    ):
                        try:
                            next_cursor = record_relabel(
                                selected_assignment.assignment_id,
                                objects,
                                ReviewCursor(object_index, False),
                                repository,
                                candidate.class_id,
                            )
                        except (OSError, ValueError) as exc:
                            st.error(f"Could not save this change: {exc}")
                        else:
                            set_cursor(next_cursor, objects)
                            st.rerun()

with st.sidebar:
    problems = repository.list_problems(selected_assignment.assignment_id)
    with st.expander(f"Problems ({len(problems)})"):
        if not problems:
            st.caption("No dataset problems found.")
        for problem_path, message in problems:
            st.markdown(f"- `{problem_path}` — {message}")

    with st.expander("Export corrected labels"):
        export = build_export(selected_assignment.assignment_id, dataset.root, repository)
        st.download_button(
            "Download results ZIP",
            data=export.content,
            file_name=export.filename,
            mime="application/zip",
            width="stretch",
        )
