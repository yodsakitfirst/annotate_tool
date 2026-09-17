from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from annotate_tool.progress import ProgressRepository
from annotate_tool.storage import atomic_relabel, build_export


def make_assignment(tmp_path: Path) -> tuple[str, Path, ProgressRepository]:
    assignment_id = "assignment-1"
    root = tmp_path / "assignment"
    (root / "labels").mkdir(parents=True)
    (root / "labels" / "a.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (root / "images").mkdir()
    (root / "images" / "a.jpg").write_bytes(b"not exported")
    (root / "backups" / "labels_original").mkdir(parents=True)
    (root / "backups" / "labels_original" / "a.txt").write_text(
        "1 0.5 0.5 0.2 0.2\n", encoding="utf-8"
    )
    (root / "classes.txt").write_text("\n".join(f"Product {i}" for i in range(89)), encoding="utf-8")
    repository = ProgressRepository(tmp_path / "progress.sqlite3")
    repository.initialize()
    repository.register_assignment(assignment_id, "Assignment", root)
    return assignment_id, root, repository


def test_atomic_relabel_preserves_all_coordinate_text(tmp_path):
    label = tmp_path / "a.txt"
    label.write_text("42 0.5220 0.433 0.13500 0.271\n", encoding="utf-8")

    atomic_relabel(label, 0, "42 0.5220 0.433 0.13500 0.271", 17)

    assert label.read_text(encoding="utf-8") == "17 0.5220 0.433 0.13500 0.271\n"


def test_atomic_relabel_rejects_stale_file_without_writing(tmp_path):
    label = tmp_path / "a.txt"
    original = "2 0.5 0.5 0.2 0.2\n"
    label.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="changed since it was loaded"):
        atomic_relabel(label, 0, "3 0.5 0.5 0.2 0.2", 4)

    assert label.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".a.txt.*.tmp")) == []


def test_failed_replace_leaves_old_label_and_removes_temporary_file(tmp_path, monkeypatch):
    label = tmp_path / "a.txt"
    original = "2 0.5 0.5 0.2 0.2\n"
    label.write_text(original, encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("disk failure")

    monkeypatch.setattr("annotate_tool.storage.os.replace", fail_replace)

    with pytest.raises(OSError, match="disk failure"):
        atomic_relabel(label, 0, "2 0.5 0.5 0.2 0.2", 4)

    assert label.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".a.txt.*.tmp")) == []


def test_export_contains_labels_metadata_progress_and_problems(tmp_path):
    assignment_id, root, repository = make_assignment(tmp_path)
    repository.record_decision(assignment_id, "images/a.jpg", 0, "relabel", 1, 7)
    repository.record_problem(assignment_id, "labels/b.txt", "malformed annotation")

    result = build_export(assignment_id, root, repository)

    with ZipFile(BytesIO(result.content)) as archive:
        names = set(archive.namelist())
        progress = json.loads(archive.read("progress.json"))
        problems = archive.read("problems.csv").decode("utf-8")
    assert "labels/a.txt" in names
    assert "classes.txt" in names
    assert "progress.json" in names
    assert "problems.csv" in names
    assert not any(name.startswith("images/") or name.startswith("backups/") for name in names)
    assert progress["summary"]["relabel"] == 1
    assert progress["decisions"][0]["resulting_class_id"] == 7
    assert "labels/b.txt,malformed annotation" in problems
    assert result.filename == "assignment-1_corrected_labels.zip"


def test_export_includes_data_yaml_when_classes_text_is_absent(tmp_path):
    assignment_id, root, repository = make_assignment(tmp_path)
    (root / "classes.txt").unlink()
    (root / "data.yaml").write_text("names: []\n", encoding="utf-8")

    result = build_export(assignment_id, root, repository)

    with ZipFile(BytesIO(result.content)) as archive:
        assert "data.yaml" in archive.namelist()
