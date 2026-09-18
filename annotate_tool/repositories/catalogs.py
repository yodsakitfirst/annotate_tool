from dataclasses import dataclass
from pathlib import Path

from annotate_tool.v2.database import Database


@dataclass(frozen=True)
class CatalogRecord:
    id: str
    name: str
    storage_root: Path
    created_at: str
    class_count: int


@dataclass(frozen=True)
class CatalogClassRecord:
    catalog_id: str
    class_id: int
    name: str
    reference_path: Path


class CatalogRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        *,
        catalog_id: str,
        name: str,
        storage_root: Path,
        classes: tuple[tuple[int, str, Path], ...],
        created_at: str,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO catalogs (id, name, storage_root, created_at) VALUES (?, ?, ?, ?)",
                (catalog_id, name.strip(), str(storage_root.resolve()), created_at),
            )
            connection.executemany(
                "INSERT INTO catalog_classes (catalog_id, class_id, name, reference_path) VALUES (?, ?, ?, ?)",
                ((catalog_id, class_id, class_name, str(path.resolve())) for class_id, class_name, path in classes),
            )

    def get(self, catalog_id: str) -> CatalogRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT c.*, COUNT(cc.class_id) AS class_count
                   FROM catalogs c LEFT JOIN catalog_classes cc ON cc.catalog_id = c.id
                   WHERE c.id = ? GROUP BY c.id""",
                (catalog_id,),
            ).fetchone()
        if row is None:
            raise KeyError(catalog_id)
        return CatalogRecord(row["id"], row["name"], Path(row["storage_root"]), row["created_at"], row["class_count"])

    def list(self, query: str = "", limit: int = 100, offset: int = 0) -> tuple[CatalogRecord, ...]:
        pattern = f"%{query.strip()}%"
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT c.*, COUNT(cc.class_id) AS class_count
                   FROM catalogs c LEFT JOIN catalog_classes cc ON cc.catalog_id = c.id
                   WHERE c.name LIKE ? COLLATE NOCASE
                   GROUP BY c.id ORDER BY c.created_at DESC, c.id LIMIT ? OFFSET ?""",
                (pattern, limit, offset),
            ).fetchall()
        return tuple(CatalogRecord(row["id"], row["name"], Path(row["storage_root"]), row["created_at"], row["class_count"]) for row in rows)

    def list_classes(self, catalog_id: str, query: str = "", limit: int = 100, offset: int = 0) -> tuple[CatalogClassRecord, ...]:
        normalized = query.strip()
        if normalized.isdecimal():
            where, arguments = "catalog_id = ? AND class_id = ?", (catalog_id, int(normalized))
        else:
            where, arguments = "catalog_id = ? AND name LIKE ? COLLATE NOCASE", (catalog_id, f"%{normalized}%")
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM catalog_classes WHERE {where} ORDER BY class_id LIMIT ? OFFSET ?",
                (*arguments, limit, offset),
            ).fetchall()
        return tuple(CatalogClassRecord(row["catalog_id"], row["class_id"], row["name"], Path(row["reference_path"])) for row in rows)

    def has_class(self, catalog_id: str, class_id: int) -> bool:
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM catalog_classes WHERE catalog_id = ? AND class_id = ?",
                (catalog_id, class_id),
            ).fetchone() is not None

    def get_class(self, catalog_id: str, class_id: int) -> CatalogClassRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM catalog_classes WHERE catalog_id = ? AND class_id = ?",
                (catalog_id, class_id),
            ).fetchone()
        if row is None:
            raise KeyError((catalog_id, class_id))
        return CatalogClassRecord(row["catalog_id"], row["class_id"], row["name"], Path(row["reference_path"]))
