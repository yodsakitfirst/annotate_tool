from pathlib import Path

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
