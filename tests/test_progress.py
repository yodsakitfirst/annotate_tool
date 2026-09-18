from pathlib import Path
import sqlite3

import pytest

from annotate_tool.progress import ProgressRepository


def prepared_repository(tmp_path: Path) -> ProgressRepository:
    repo = ProgressRepository(tmp_path / "progress.sqlite3")
    repo.initialize()
    repo.register_assignment("id-1", "Alice", tmp_path / "assignment")
    return repo


def test_decisions_survive_repository_restart(tmp_path):
    database = tmp_path / "progress.sqlite3"
    repo = ProgressRepository(database)
    repo.initialize()
    repo.register_assignment("id-1", "Alice", tmp_path / "assignment")
    repo.record_decision("id-1", "images/a.jpg", 2, "correct", 7, 7)

    reopened = ProgressRepository(database)
    reopened.initialize()

    assert reopened.reviewed_keys("id-1") == {("images/a.jpg", 2)}
    assert reopened.summary("id-1") == {
        "reviewed": 1,
        "correct": 1,
        "relabel": 0,
        "skipped": 0,
    }


def test_recording_same_object_updates_one_row(tmp_path):
    repo = prepared_repository(tmp_path)
    repo.record_decision("id-1", "images/a.jpg", 0, "skip", 4, None)
    repo.record_decision("id-1", "images/a.jpg", 0, "relabel", 4, 8)

    assert repo.summary("id-1") == {
        "reviewed": 1,
        "correct": 0,
        "relabel": 1,
        "skipped": 0,
    }
    decisions = repo.list_decisions("id-1")
    assert len(decisions) == 1
    assert decisions[0].resulting_class_id == 8


def test_skip_is_reported_but_not_reviewed(tmp_path):
    repo = prepared_repository(tmp_path)
    repo.record_decision("id-1", "images/a.jpg", 0, "skip", 4, None)

    assert repo.reviewed_keys("id-1") == set()
    assert repo.summary("id-1")["skipped"] == 1


def test_assignments_are_listed_newest_first_and_registration_is_idempotent(tmp_path):
    repo = ProgressRepository(tmp_path / "nested" / "progress.sqlite3")
    repo.initialize()
    repo.register_assignment("id-1", "Alice", tmp_path / "a")
    repo.register_assignment("id-2", "Bob", tmp_path / "b")
    repo.register_assignment("id-1", "Alice renamed", tmp_path / "a")

    assignments = repo.list_assignments()

    assert [item.assignment_id for item in assignments] == ["id-2", "id-1"]
    assert assignments[1].display_name == "Alice renamed"


def test_invalid_decision_is_rejected(tmp_path):
    repo = prepared_repository(tmp_path)

    with pytest.raises(ValueError, match="decision"):
        repo.record_decision("id-1", "images/a.jpg", 0, "invalid", 4, 4)


def test_decision_requires_registered_assignment(tmp_path):
    repo = ProgressRepository(tmp_path / "progress.sqlite3")
    repo.initialize()

    with pytest.raises(ValueError, match="registered assignment"):
        repo.record_decision("missing", "images/a.jpg", 0, "correct", 4, 4)


def test_problems_persist_without_duplicates(tmp_path):
    repo = prepared_repository(tmp_path)
    repo.record_problem("id-1", "labels/a.txt", "bad line")
    repo.record_problem("id-1", "labels/a.txt", "bad line")

    reopened = ProgressRepository(tmp_path / "progress.sqlite3")
    reopened.initialize()

    assert reopened.list_problems("id-1") == (("labels/a.txt", "bad line"),)


def test_initialize_migrates_legacy_assignment_without_losing_progress(tmp_path):
    database = tmp_path / "progress.sqlite3"
    dataset_root = tmp_path / "assignment-1"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE assignments (
                assignment_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                root TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE decisions (
                assignment_id TEXT NOT NULL,
                image_path TEXT NOT NULL,
                line_index INTEGER NOT NULL,
                decision TEXT NOT NULL,
                previous_class_id INTEGER NOT NULL,
                resulting_class_id INTEGER,
                decided_at TEXT NOT NULL,
                PRIMARY KEY (assignment_id, image_path, line_index)
            );
            """
        )
        connection.execute(
            "INSERT INTO assignments VALUES (?, ?, ?, ?)",
            ("assignment-1", "Legacy", str(dataset_root), "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("assignment-1", "images/a.jpg", 0, "correct", 7, 7, "2026-01-01T00:01:00+00:00"),
        )

    repository = ProgressRepository(database)
    repository.initialize()

    project = repository.get_project("assignment-1")
    assert project.dataset_root == dataset_root
    assert project.reference_root is None
    assert repository.summary("assignment-1")["reviewed"] == 1


def test_project_owner_controls_edit_access(tmp_path):
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    repository.register_project(
        "p1",
        "Hair 001",
        tmp_path / "dataset",
        tmp_path / "references",
    )
    repository.assign_project("p1", "Alice")

    assert repository.get_project("p1").owner_name == "Alice"
    assert repository.can_edit_project("p1", "Alice")
    assert not repository.can_edit_project("p1", "Bob")


def test_blank_project_owner_is_rejected(tmp_path):
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    repository.register_project("p1", "Hair 001", tmp_path / "dataset", None)

    with pytest.raises(ValueError, match="owner"):
        repository.assign_project("p1", "   ")
