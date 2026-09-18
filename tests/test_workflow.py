from pathlib import Path

from PIL import Image
import pytest

from annotate_tool.dataset import load_assignment
from annotate_tool.progress import ProgressRepository
from annotate_tool.workflow import (
    ReviewCursor,
    flatten_objects,
    move_cursor,
    record_correct,
    record_relabel,
    record_skip,
    resume_cursor,
)


@pytest.fixture
def workflow_fixture(dataset_root):
    dataset = load_assignment(dataset_root)
    objects = flatten_objects(dataset)
    repository = ProgressRepository(dataset_root.parent / "progress.sqlite3")
    repository.initialize()
    repository.register_assignment("dataset-1", "Dataset", dataset_root)
    return {
        "dataset_id": "dataset-1",
        "dataset": dataset,
        "objects": objects,
        "cursor": ReviewCursor(0, False),
        "repository": repository,
        "label_path": dataset_root / "labels" / "a.txt",
    }


def action_args(fixture):
    return {
        "dataset_id": fixture["dataset_id"],
        "objects": fixture["objects"],
        "cursor": fixture["cursor"],
        "repository": fixture["repository"],
    }


def test_resume_selects_first_unreviewed_valid_object(workflow_fixture):
    first = workflow_fixture["objects"][0]
    workflow_fixture["repository"].record_decision(
        workflow_fixture["dataset_id"], first.image_path, first.line_index, "correct", 3, 3
    )

    cursor = resume_cursor(
        workflow_fixture["dataset_id"],
        workflow_fixture["objects"],
        workflow_fixture["repository"],
    )

    assert cursor == ReviewCursor(1, False)


def test_correct_persists_and_advances_without_touching_label(workflow_fixture):
    before = workflow_fixture["label_path"].read_bytes()

    cursor = record_correct(**action_args(workflow_fixture))

    assert workflow_fixture["label_path"].read_bytes() == before
    assert workflow_fixture["repository"].summary(workflow_fixture["dataset_id"])["correct"] == 1
    assert cursor == ReviewCursor(1, False)


def test_relabel_edits_expected_object_records_progress_and_advances(workflow_fixture):
    cursor = record_relabel(new_class_id=8, **action_args(workflow_fixture))

    assert workflow_fixture["label_path"].read_text(encoding="utf-8").splitlines()[0].startswith("8 ")
    assert workflow_fixture["repository"].summary(workflow_fixture["dataset_id"])["relabel"] == 1
    assert cursor == ReviewCursor(1, False)


def test_skip_advances_but_remains_available_on_next_resume(workflow_fixture):
    advanced = record_skip(**action_args(workflow_fixture))
    resumed = resume_cursor(
        workflow_fixture["dataset_id"],
        workflow_fixture["objects"],
        workflow_fixture["repository"],
    )

    assert advanced == ReviewCursor(1, False)
    assert resumed == ReviewCursor(0, False)


def test_failed_stale_relabel_does_not_record_progress(workflow_fixture):
    workflow_fixture["label_path"].write_text(
        "9 0.5 0.5 0.2 0.2\n17 0.2 0.25 0.1 0.2\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="changed since it was loaded"):
        record_relabel(new_class_id=8, **action_args(workflow_fixture))

    assert workflow_fixture["repository"].summary(workflow_fixture["dataset_id"])["reviewed"] == 0


def test_all_reviewed_returns_complete_cursor(workflow_fixture):
    repository = workflow_fixture["repository"]
    for item in workflow_fixture["objects"]:
        repository.record_decision(
            workflow_fixture["dataset_id"],
            item.image_path,
            item.line_index,
            "correct",
            item.annotation.class_id,
            item.annotation.class_id,
        )

    cursor = resume_cursor(workflow_fixture["dataset_id"], workflow_fixture["objects"], repository)

    assert cursor == ReviewCursor(None, True)


def test_zero_object_dataset_is_complete(dataset_root):
    (dataset_root / "labels" / "a.txt").write_text("", encoding="utf-8")
    dataset = load_assignment(dataset_root)
    repository = ProgressRepository(dataset_root.parent / "progress.sqlite3")
    repository.initialize()
    repository.register_assignment("dataset-1", "Dataset", dataset_root)

    assert flatten_objects(dataset) == ()
    assert resume_cursor("dataset-1", (), repository) == ReviewCursor(None, True)


def test_flattening_and_navigation_cross_image_boundaries(dataset_root):
    Image.new("RGB", (30, 30), "white").save(dataset_root / "images" / "b.jpg")
    (dataset_root / "labels" / "b.txt").write_text("4 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    objects = flatten_objects(load_assignment(dataset_root))

    assert [item.image_index for item in objects] == [0, 0, 1]
    assert move_cursor(ReviewCursor(1, False), objects, 1) == ReviewCursor(2, False)
    assert move_cursor(ReviewCursor(2, False), objects, 1) == ReviewCursor(2, False)
    assert move_cursor(ReviewCursor(0, False), objects, -1) == ReviewCursor(0, False)


def test_non_owner_cannot_relabel(workflow_fixture):
    repository = workflow_fixture["repository"]
    repository.assign_project(workflow_fixture["dataset_id"], "Alice")

    with pytest.raises(PermissionError, match="assigned to Alice"):
        record_relabel(
            new_class_id=8,
            annotator_name="Bob",
            allowed_class_ids={8},
            **action_args(workflow_fixture),
        )


def test_correct_rejects_source_id_outside_reference_catalog(workflow_fixture):
    with pytest.raises(ValueError, match="reference catalog"):
        record_correct(
            annotator_name=None,
            allowed_class_ids={17},
            **action_args(workflow_fixture),
        )
