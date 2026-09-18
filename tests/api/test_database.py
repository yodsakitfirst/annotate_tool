from pathlib import Path

import pytest

from annotate_tool.repositories.annotations import AnnotationRepository
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.repositories.projects import ProjectRepository
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.database import Database


def prepared_database(tmp_path: Path) -> tuple[Database, V2Paths]:
    paths = V2Paths.from_root(tmp_path / "data")
    paths.ensure()
    database = Database(paths.database)
    database.initialize()
    return database, paths


def test_initialize_is_idempotent_and_configures_sqlite(tmp_path):
    database, paths = prepared_database(tmp_path)

    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert paths.database.is_file()
    assert {
        "catalogs",
        "catalog_classes",
        "projects",
        "images",
        "annotations",
        "import_problems",
        "legacy_catalog_migrations",
    } <= tables


def test_catalog_repository_preserves_sparse_ids_and_searches_names(tmp_path):
    database, paths = prepared_database(tmp_path)
    repository = CatalogRepository(database)
    root = paths.catalogs / "catalog-1"

    repository.create(
        catalog_id="catalog-1",
        name="Hair products",
        storage_root=root,
        classes=((1, "Alpha", root / "images/1.png"), (7, "Omega", root / "images/7.webp")),
        created_at="2026-09-18T00:00:00+00:00",
    )

    assert [item.class_id for item in repository.list_classes("catalog-1")] == [1, 7]
    assert [item.class_id for item in repository.list_classes("catalog-1", query="mega")] == [7]
    assert repository.get("catalog-1").class_count == 2


def test_project_summary_and_annotation_update_are_database_backed(tmp_path, monkeypatch):
    database, paths = prepared_database(tmp_path)
    catalogs = CatalogRepository(database)
    projects = ProjectRepository(database)
    annotations = AnnotationRepository(database)
    catalog_root = paths.catalogs / "catalog-1"
    project_root = paths.projects / "project-1" / "dataset"
    catalogs.create(
        catalog_id="catalog-1",
        name="Targets",
        storage_root=catalog_root,
        classes=((7, "Seven", catalog_root / "images/7.png"),),
        created_at="2026-09-18T00:00:00+00:00",
    )
    projects.create(
        project_id="project-1",
        name="Dataset A",
        catalog_id="catalog-1",
        dataset_root=project_root,
        created_at="2026-09-18T00:01:00+00:00",
        images=(
            {
                "id": "image-1",
                "relative_path": "images/a.jpg",
                "image_path": project_root / "images/a.jpg",
                "label_path": project_root / "labels/a.txt",
                "width": 100,
                "height": 80,
                "sort_index": 0,
                "error_message": None,
                "annotations": (
                    {
                        "id": "annotation-1",
                        "line_index": 0,
                        "source_class_id": 999,
                        "current_class_id": 999,
                        "coordinates": ("0.5", "0.5", "0.2", "0.4"),
                        "original_line": "999 0.5 0.5 0.2 0.4",
                    },
                ),
            },
        ),
        problems=(),
    )

    monkeypatch.setattr(Path, "rglob", lambda *_args, **_kwargs: pytest.fail("filesystem scan"))
    summary = projects.list()[0]
    assert (summary.image_count, summary.annotation_count, summary.reviewed_count) == (1, 1, 0)

    updated = annotations.update_decision(
        "annotation-1",
        decision="relabel",
        target_class_id=7,
        annotator_name="Ada",
        updated_at="2026-09-18T00:02:00+00:00",
    )
    assert updated.current_class_id == 7
    assert updated.version == 1
    assert projects.list()[0].reviewed_count == 1
