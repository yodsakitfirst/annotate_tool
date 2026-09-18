from dataclasses import dataclass
from pathlib import Path
from collections.abc import Collection

from annotate_tool.models import Annotation, AssignmentDataset
from annotate_tool.progress import ProgressRepository
from annotate_tool.storage import atomic_relabel


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


def flatten_objects(dataset: AssignmentDataset) -> tuple[ObjectKey, ...]:
    objects: list[ObjectKey] = []
    for image_index, record in enumerate(dataset.images):
        if record.image_error is not None or record.parse_result.problems:
            continue
        for annotation in record.parse_result.annotations:
            objects.append(
                ObjectKey(
                    image_index=image_index,
                    image_path=record.relative_path,
                    label_path=record.label_path,
                    line_index=annotation.line_index,
                    annotation=annotation,
                )
            )
    return tuple(objects)


def resume_cursor(
    dataset_id: str,
    objects: tuple[ObjectKey, ...],
    repository: ProgressRepository,
) -> ReviewCursor:
    reviewed = repository.reviewed_keys(dataset_id)
    for index, item in enumerate(objects):
        if (item.image_path, item.line_index) not in reviewed:
            return ReviewCursor(index, False)
    return ReviewCursor(None, True)


def move_cursor(
    cursor: ReviewCursor,
    objects: tuple[ObjectKey, ...],
    delta: int,
) -> ReviewCursor:
    if not objects:
        return ReviewCursor(None, True)
    if cursor.object_index is None:
        return ReviewCursor(0 if delta >= 0 else len(objects) - 1, False)
    return ReviewCursor(max(0, min(len(objects) - 1, cursor.object_index + delta)), False)


def _selected(objects: tuple[ObjectKey, ...], cursor: ReviewCursor) -> tuple[int, ObjectKey]:
    if cursor.object_index is None or not 0 <= cursor.object_index < len(objects):
        raise ValueError("no review object is selected")
    return cursor.object_index, objects[cursor.object_index]


def _require_project_owner(
    dataset_id: str,
    repository: ProgressRepository,
    annotator_name: str | None,
) -> None:
    if annotator_name is None:
        return
    project = repository.get_project(dataset_id)
    if project.owner_name != annotator_name.strip():
        owner = project.owner_name or "no annotator"
        raise PermissionError(f"project is assigned to {owner}")


def _next_unreviewed(
    dataset_id: str,
    objects: tuple[ObjectKey, ...],
    current_index: int,
    repository: ProgressRepository,
    skipped_current: bool = False,
) -> ReviewCursor:
    reviewed = repository.reviewed_keys(dataset_id)
    for offset in range(1, len(objects) + 1):
        index = (current_index + offset) % len(objects)
        if skipped_current and index == current_index:
            continue
        item = objects[index]
        if (item.image_path, item.line_index) not in reviewed:
            return ReviewCursor(index, False)
    if skipped_current:
        return ReviewCursor(current_index, False)
    return ReviewCursor(None, True)


def record_correct(
    dataset_id: str,
    objects: tuple[ObjectKey, ...],
    cursor: ReviewCursor,
    repository: ProgressRepository,
    annotator_name: str | None = None,
    allowed_class_ids: Collection[int] | None = None,
) -> ReviewCursor:
    _require_project_owner(dataset_id, repository, annotator_name)
    current_index, item = _selected(objects, cursor)
    if allowed_class_ids is not None and item.annotation.class_id not in frozenset(allowed_class_ids):
        raise ValueError(
            f"class ID {item.annotation.class_id} is not in the project reference catalog"
        )
    repository.record_decision(
        dataset_id,
        item.image_path,
        item.line_index,
        "correct",
        item.annotation.class_id,
        item.annotation.class_id,
        annotator_name=annotator_name,
    )
    return _next_unreviewed(dataset_id, objects, current_index, repository)


def record_relabel(
    dataset_id: str,
    objects: tuple[ObjectKey, ...],
    cursor: ReviewCursor,
    repository: ProgressRepository,
    new_class_id: int,
    allowed_class_ids: Collection[int] | None = None,
    annotator_name: str | None = None,
) -> ReviewCursor:
    _require_project_owner(dataset_id, repository, annotator_name)
    current_index, item = _selected(objects, cursor)
    atomic_relabel(
        item.label_path,
        item.line_index,
        item.annotation.original_line,
        new_class_id,
        allowed_class_ids=allowed_class_ids,
    )
    repository.record_decision(
        dataset_id,
        item.image_path,
        item.line_index,
        "relabel",
        item.annotation.class_id,
        new_class_id,
        annotator_name=annotator_name,
    )
    return _next_unreviewed(dataset_id, objects, current_index, repository)


def record_skip(
    dataset_id: str,
    objects: tuple[ObjectKey, ...],
    cursor: ReviewCursor,
    repository: ProgressRepository,
    annotator_name: str | None = None,
) -> ReviewCursor:
    _require_project_owner(dataset_id, repository, annotator_name)
    current_index, item = _selected(objects, cursor)
    repository.record_decision(
        dataset_id,
        item.image_path,
        item.line_index,
        "skip",
        item.annotation.class_id,
        None,
        annotator_name=annotator_name,
    )
    return _next_unreviewed(
        dataset_id,
        objects,
        current_index,
        repository,
        skipped_current=True,
    )
