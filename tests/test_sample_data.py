from zipfile import ZipFile

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.dataset import load_assignment, source_class_name
from annotate_tool.project_importer import import_project
from scripts.create_sample_data import create_sample_project_archives


def test_sample_project_uses_sparse_catalog_and_arbitrary_source_id(tmp_path):
    dataset_path, catalog_path = create_sample_project_archives(
        tmp_path / "sample_dataset.zip",
        tmp_path / "sample_catalog.zip",
    )

    with ZipFile(dataset_path) as archive:
        names = set(archive.namelist())
    assert "images/multiple_boxes.jpg" in names
    assert "labels/empty.txt" in names
    assert "images/missing_label.jpg" in names
    assert "labels/malformed.txt" in names
    assert not any(name.startswith("references/") for name in names)

    imported = import_project(
        dataset_path,
        catalog_path,
        "Sample",
        "Alice",
        AppPaths.from_root(tmp_path / "runtime"),
        ImportLimits(),
    )
    dataset = load_assignment(
        imported.dataset_root,
        reference_classes=imported.reference_classes,
    )
    assert [item.class_id for item in dataset.classes] == [3, 17, 20]
    assert all(item.reference_path.is_file() for item in dataset.classes)
    assert source_class_name(dataset, 9999) == "Unknown source class 9999"
    assert len(dataset.images) == 4
    assert len(dataset.images[-1].parse_result.annotations) == 2
