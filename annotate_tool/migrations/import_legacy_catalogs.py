from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sqlite3

import yaml

from annotate_tool.reference_catalog import load_reference_catalog
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.database import Database
from annotate_tool.v2.filesystem import publish_directory


@dataclass(frozen=True)
class MigrationSummary:
    imported: int
    skipped: int
    failed: int
    failures: tuple[str, ...] = ()


def _legacy_database(root: Path) -> Path:
    for name in ("progress.sqlite3", "app.db", "app.sqlite3"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("No legacy SQLite database was found")


def _catalog_groups(database_path: Path) -> tuple[tuple[str, str, tuple[sqlite3.Row, ...]], ...]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "reference_classes" not in tables or "assignments" not in tables:
            return ()
        projects = connection.execute(
            """SELECT a.assignment_id, a.display_name
               FROM assignments a
               WHERE EXISTS (SELECT 1 FROM reference_classes r WHERE r.assignment_id = a.assignment_id)
               ORDER BY a.assignment_id"""
        ).fetchall()
        return tuple(
            (
                project["assignment_id"],
                project["display_name"],
                tuple(
                    connection.execute(
                        """SELECT class_id, display_name, image_path
                           FROM reference_classes WHERE assignment_id = ?
                           ORDER BY class_id""",
                        (project["assignment_id"],),
                    ).fetchall()
                ),
            )
            for project in projects
        )
    finally:
        connection.close()


def _fingerprint(rows: tuple[sqlite3.Row, ...]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        image_path = Path(row["image_path"])
        digest.update(str(row["class_id"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(row["display_name"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(image_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _already_migrated(database: Database, fingerprint: str) -> bool:
    with database.connect() as connection:
        return connection.execute(
            "SELECT 1 FROM legacy_catalog_migrations WHERE fingerprint = ?", (fingerprint,)
        ).fetchone() is not None


def _publish_catalog(paths: V2Paths, repository: CatalogRepository, display_name: str, rows: tuple[sqlite3.Row, ...], fingerprint: str) -> str:
    catalog_id = f"legacy-{fingerprint[:24]}"
    final_root = paths.catalogs / catalog_id
    if not final_root.exists():
        staged_root = paths.staging / f"catalog-{catalog_id}"
        image_root = staged_root / "images"
        image_root.mkdir(parents=True)
        try:
            names: dict[int, str] = {}
            for row in rows:
                class_id = int(row["class_id"])
                name = str(row["display_name"]).strip()
                source = Path(row["image_path"])
                if class_id < 0 or not name or not source.is_file():
                    raise ValueError(f"Invalid legacy reference class {class_id}")
                names[class_id] = name
                shutil.copy2(source, image_root / f"{class_id}{source.suffix.casefold()}")
            (staged_root / "catalog.yaml").write_text(
                yaml.safe_dump({"names": names}, sort_keys=True, allow_unicode=True),
                encoding="utf-8",
            )
            load_reference_catalog(staged_root)
            (staged_root / ".complete").write_text("complete\n", encoding="utf-8")
            publish_directory(staged_root, final_root, paths.staging, paths.catalogs)
        finally:
            if staged_root.exists():
                shutil.rmtree(staged_root)

    try:
        repository.get(catalog_id)
    except KeyError:
        classes = load_reference_catalog(final_root)
        repository.create(
            catalog_id=catalog_id,
            name=f"Legacy: {display_name}",
            storage_root=final_root,
            classes=tuple((item.class_id, item.name, item.reference_path) for item in classes if item.reference_path),
            created_at=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        )
    return catalog_id


def import_legacy_catalogs(legacy_root: Path, target_root: Path) -> MigrationSummary:
    legacy_root = legacy_root.resolve()
    paths = V2Paths.from_root(target_root)
    paths.ensure()
    database = Database(paths.database)
    database.initialize()
    repository = CatalogRepository(database)
    imported = skipped = failed = 0
    failures: list[str] = []
    for assignment_id, display_name, rows in _catalog_groups(_legacy_database(legacy_root)):
        try:
            fingerprint = _fingerprint(rows)
            if _already_migrated(database, fingerprint):
                skipped += 1
                continue
            catalog_id = _publish_catalog(paths, repository, display_name, rows, fingerprint)
            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO legacy_catalog_migrations (fingerprint, catalog_id, imported_at) VALUES (?, ?, ?)",
                    (fingerprint, catalog_id, datetime.now(timezone.utc).isoformat(timespec="microseconds")),
                )
            imported += 1
        except Exception as exc:
            failed += 1
            failures.append(f"{assignment_id}: {exc}")
    return MigrationSummary(imported, skipped, failed, tuple(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import reusable catalogs from a legacy annotation workspace")
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = import_legacy_catalogs(args.legacy_root, args.target_root)
    except Exception as exc:
        print(f"Migration failed: {exc}")
        return 1
    print(f"Imported: {summary.imported}; skipped: {summary.skipped}; failed: {summary.failed}")
    for failure in summary.failures:
        print(f"- {failure}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
