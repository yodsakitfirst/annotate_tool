from zipfile import ZipFile

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.importer import import_assignment
from annotate_tool.dataset import load_assignment
from scripts.create_sample_data import create_sample_archive


def test_sample_archive_contains_89_references_and_imports(tmp_path):
    archive_path = create_sample_archive(tmp_path / "sample_assignment.zip")

    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "images/multiple_boxes.jpg" in names
    assert "labels/empty.txt" in names
    assert "images/missing_label.jpg" in names
    assert "labels/malformed.txt" in names
    assert len([name for name in names if name.startswith("references/")]) == 89

    imported = import_assignment(
        archive_path,
        "Sample",
        AppPaths.from_root(tmp_path / "runtime"),
        ImportLimits(),
    )
    dataset = load_assignment(imported.root)
    assert len(dataset.classes) == 89
    assert len(dataset.images) == 4
    assert len(dataset.images[-1].parse_result.annotations) == 2
