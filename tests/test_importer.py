import stat
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.importer import (
    AssignmentImportError,
    ensure_original_backup,
    import_assignment,
)


def classes_text() -> str:
    return "\n".join(f"Product {class_id:02d}" for class_id in range(89)) + "\n"


def make_zip(tmp_path: Path, members: dict[str, bytes], name: str = "dataset.zip") -> Path:
    archive = tmp_path / name
    with ZipFile(archive, "w") as output:
        for member, content in members.items():
            output.writestr(member, content)
    return archive


def create_assignment_tree(tmp_path: Path) -> Path:
    assignment = tmp_path / "assignment"
    (assignment / "images").mkdir(parents=True)
    (assignment / "labels").mkdir()
    (assignment / "labels" / "a.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (assignment / "classes.txt").write_text(classes_text(), encoding="utf-8")
    return assignment


def test_import_accepts_single_wrapper_directory(tmp_path):
    archive = make_zip(
        tmp_path,
        {
            "batch/images/a.jpg": b"image-bytes",
            "batch/labels/a.txt": b"1 0.5 0.5 0.2 0.2\n",
            "batch/classes.txt": classes_text().encode(),
        },
    )
    paths = AppPaths.from_root(tmp_path / "runtime")

    imported = import_assignment(archive, "Alice batch", paths, ImportLimits())

    assert imported.display_name == "Alice batch"
    assert (imported.root / "images" / "a.jpg").exists()
    assert (imported.root / "source_name.txt").read_text(encoding="utf-8") == "Alice batch\n"
    assert (imported.root / "backups" / "labels_original" / "a.txt").read_bytes().startswith(b"1 ")


@pytest.mark.parametrize("member", ["../escape.txt", "/absolute.txt", "C:/drive.txt"])
def test_import_rejects_unsafe_paths(tmp_path, member):
    archive = make_zip(tmp_path, {member: b"bad"})

    with pytest.raises(AssignmentImportError, match="unsafe archive path"):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "runtime"), ImportLimits())


def test_import_rejects_symlink_entries(tmp_path):
    archive = tmp_path / "symlink.zip"
    link = ZipInfo("images/link.jpg")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(archive, "w") as output:
        output.writestr(link, "target.jpg")

    with pytest.raises(AssignmentImportError, match="symbolic link"):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "runtime"), ImportLimits())


def test_import_rejects_case_insensitive_duplicate_destinations(tmp_path):
    archive = make_zip(tmp_path, {"images/A.jpg": b"a", "images/a.jpg": b"b"})

    with pytest.raises(AssignmentImportError, match="duplicate archive destination"):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "runtime"), ImportLimits())


def test_import_enforces_file_and_uncompressed_size_limits(tmp_path):
    archive = make_zip(tmp_path, {"images/a.jpg": b"1234", "classes.txt": b"x"})

    with pytest.raises(AssignmentImportError, match="too many files"):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "one"), ImportLimits(max_files=1))
    with pytest.raises(AssignmentImportError, match="too large"):
        import_assignment(
            archive,
            "Bad",
            AppPaths.from_root(tmp_path / "two"),
            ImportLimits(max_uncompressed_bytes=4),
        )


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ({"classes.txt": b"x"}, "images"),
        ({"images/a.jpg": b"x"}, "class metadata"),
    ],
)
def test_import_requires_dataset_structure(tmp_path, members, message):
    archive = make_zip(tmp_path, members)

    with pytest.raises(AssignmentImportError, match=message):
        import_assignment(archive, "Bad", AppPaths.from_root(tmp_path / "runtime"), ImportLimits())


def test_import_rejects_blank_display_name_and_removes_staging_files(tmp_path):
    archive = make_zip(tmp_path, {"images/a.jpg": b"x", "classes.txt": b"x"})
    paths = AppPaths.from_root(tmp_path / "runtime")

    with pytest.raises(AssignmentImportError, match="display name"):
        import_assignment(archive, "   ", paths, ImportLimits())

    assert not paths.staging.exists() or list(paths.staging.iterdir()) == []


def test_existing_backup_is_never_overwritten(tmp_path):
    assignment = create_assignment_tree(tmp_path)
    backup = ensure_original_backup(assignment)
    (assignment / "labels" / "a.txt").write_text("9 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    second = ensure_original_backup(assignment)

    assert second == backup
    assert (backup / "a.txt").read_text(encoding="utf-8").startswith("1 ")


def test_backup_succeeds_when_windows_denies_directory_renames(tmp_path, monkeypatch):
    assignment = create_assignment_tree(tmp_path)

    def deny_directory_rename(source, destination):
        raise PermissionError(5, "Access is denied", str(source), str(destination))

    monkeypatch.setattr("annotate_tool.importer.os.replace", deny_directory_rename)

    backup = ensure_original_backup(assignment)

    assert (backup / "a.txt").read_text(encoding="utf-8") == "1 0.5 0.5 0.2 0.2\n"
    assert (assignment / "backups" / ".backup_complete").is_file()
