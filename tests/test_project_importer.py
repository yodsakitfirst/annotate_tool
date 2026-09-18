from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
import pytest
import yaml

from annotate_tool.config import AppPaths, ImportLimits
import annotate_tool.project_importer as project_importer


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 6), "red").save(output, format="PNG")
    return output.getvalue()


def dataset_zip(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("images/a.png", png_bytes())
        archive.writestr("labels/a.txt", "9999 0.5 0.5 0.2 0.2\n")
        archive.writestr("data.yaml", yaml.safe_dump({"names": {9999: "Legacy"}}))
    return path


def catalog_zip(tmp_path: Path, valid: bool = True) -> Path:
    path = tmp_path / "catalog.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("catalog.yaml", yaml.safe_dump({"names": {1: "Blue", 7: "Green"}}))
        archive.writestr("references/1.png", png_bytes())
        if valid:
            archive.writestr("references/7.png", png_bytes())
    return path


def test_import_project_publishes_dataset_and_catalog_together(tmp_path):
    paths = AppPaths.from_root(tmp_path / "runtime")

    imported = project_importer.import_project(
        dataset_zip(tmp_path),
        catalog_zip(tmp_path),
        "Hair 001",
        "Alice",
        paths,
        ImportLimits(),
    )

    assert imported.dataset_root == paths.projects / imported.project_id / "dataset"
    assert imported.reference_root == paths.projects / imported.project_id / "references"
    assert imported.owner_name == "Alice"
    assert [item.class_id for item in imported.reference_classes] == [1, 7]
    assert (imported.dataset_root / "backups" / "labels_original" / "a.txt").is_file()


def test_catalog_failure_rolls_back_unregistered_project(tmp_path):
    paths = AppPaths.from_root(tmp_path / "runtime")

    with pytest.raises(project_importer.ProjectImportError, match="missing reference image"):
        project_importer.import_project(
            dataset_zip(tmp_path),
            catalog_zip(tmp_path, valid=False),
            "Hair 001",
            "Alice",
            paths,
            ImportLimits(),
        )

    assert list(paths.projects.iterdir()) == []
