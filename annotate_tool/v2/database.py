from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS catalogs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    storage_root TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_classes (
    catalog_id TEXT NOT NULL REFERENCES catalogs(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL CHECK (class_id >= 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    reference_path TEXT NOT NULL,
    PRIMARY KEY (catalog_id, class_id)
);
CREATE INDEX IF NOT EXISTS idx_catalog_classes_name ON catalog_classes(catalog_id, name);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    catalog_id TEXT NOT NULL REFERENCES catalogs(id),
    dataset_root TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    image_path TEXT NOT NULL,
    label_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    sort_index INTEGER NOT NULL,
    error_message TEXT,
    UNIQUE (project_id, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_images_project_order ON images(project_id, sort_index);

CREATE TABLE IF NOT EXISTS annotations (
    id TEXT PRIMARY KEY,
    image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    line_index INTEGER NOT NULL CHECK (line_index >= 0),
    source_class_id INTEGER NOT NULL CHECK (source_class_id >= 0),
    source_class_name TEXT NOT NULL,
    current_class_id INTEGER NOT NULL CHECK (current_class_id >= 0),
    x_center REAL NOT NULL,
    y_center REAL NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    coordinate_tokens TEXT NOT NULL,
    original_line TEXT NOT NULL,
    decision TEXT CHECK (decision IN ('correct', 'relabel', 'skip')),
    annotator_name TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    UNIQUE (image_id, line_index)
);
CREATE INDEX IF NOT EXISTS idx_annotations_image_line ON annotations(image_id, line_index);
CREATE INDEX IF NOT EXISTS idx_annotations_decision ON annotations(decision);

CREATE TABLE IF NOT EXISTS import_problems (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    line_index INTEGER,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_problems_project ON import_problems(project_id);

CREATE TABLE IF NOT EXISTS legacy_catalog_migrations (
    fingerprint TEXT PRIMARY KEY,
    catalog_id TEXT NOT NULL REFERENCES catalogs(id),
    imported_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            if immediate:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(SCHEMA)
            annotation_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(annotations)")
            }
            if "source_class_name" not in annotation_columns:
                connection.execute(
                    "ALTER TABLE annotations ADD COLUMN source_class_name TEXT NOT NULL DEFAULT ''"
                )

    def check_accessible(self) -> None:
        with self.connect() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        if row is None or row[0] != "ok":
            raise sqlite3.DatabaseError("SQLite quick check failed")
