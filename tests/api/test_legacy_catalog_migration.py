from pathlib import Path

from annotate_tool.migrations.import_legacy_catalogs import import_legacy_catalogs
from annotate_tool.models import ClassInfo
from annotate_tool.progress import ProgressRepository
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.repositories.projects import ProjectRepository
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.database import Database
from tests.api.conftest import image_bytes


def test_migrates_only_distinct_legacy_catalogs_and_is_idempotent(tmp_path: Path):
    legacy_root = tmp_path / "legacy"
    target_root = tmp_path / "target"
    references = legacy_root / "projects/p1/references/images"
    references.mkdir(parents=True)
    (references / "1.png").write_bytes(image_bytes("red"))
    (references / "7.png").write_bytes(image_bytes("blue"))
    dataset = legacy_root / "projects/p1/dataset"
    dataset.mkdir(parents=True)
    marker = dataset / "legacy-stays.txt"
    marker.write_text("untouched", encoding="utf-8")
    legacy = ProgressRepository(legacy_root / "progress.sqlite3")
    legacy.initialize()
    legacy.register_project("p1", "Dữ liệu tóc", dataset, references.parent, "Ada")
    legacy.replace_reference_classes(
        "p1",
        (
            ClassInfo(1, "Dầu gội", references / "1.png"),
            ClassInfo(7, "Kem ủ", references / "7.png"),
        ),
    )
    legacy.record_decision("p1", "images/a.png", 0, "skip", 999, None, "Ada")

    first = import_legacy_catalogs(legacy_root, target_root)
    second = import_legacy_catalogs(legacy_root, target_root)

    paths = V2Paths.from_root(target_root)
    database = Database(paths.database)
    catalogs = CatalogRepository(database)
    projects = ProjectRepository(database)
    assert (first.imported, first.skipped, first.failed) == (1, 0, 0)
    assert (second.imported, second.skipped, second.failed) == (0, 1, 0)
    assert len(catalogs.list()) == 1
    catalog = catalogs.list()[0]
    assert catalog.name == "Legacy: Dữ liệu tóc"
    assert [(item.class_id, item.name) for item in catalogs.list_classes(catalog.id)] == [
        (1, "Dầu gội"), (7, "Kem ủ")
    ]
    assert all(item.reference_path.is_file() for item in catalogs.list_classes(catalog.id))
    assert projects.list() == ()
    assert marker.read_text(encoding="utf-8") == "untouched"
    assert legacy.summary("p1")["skipped"] == 1
