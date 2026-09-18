from dataclasses import dataclass
import json
from pathlib import Path

from annotate_tool.v2.database import Database


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    catalog_id: str
    dataset_root: Path
    created_at: str
    updated_at: str
    image_count: int
    annotation_count: int
    reviewed_count: int
    thumbnail_image_id: str | None


@dataclass(frozen=True)
class ImageSummary:
    id: str
    project_id: str
    relative_path: str
    image_path: Path
    label_path: Path
    width: int | None
    height: int | None
    sort_index: int
    error_message: str | None
    annotation_count: int
    reviewed_count: int


@dataclass(frozen=True)
class ImageAnnotation:
    id: str
    line_index: int
    source_class_id: int
    source_class_name: str
    current_class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    decision: str | None
    annotator_name: str | None
    version: int


class ProjectRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        *,
        project_id: str,
        name: str,
        catalog_id: str,
        dataset_root: Path,
        created_at: str,
        images: tuple[dict, ...],
        problems: tuple[dict, ...],
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO projects (id, name, catalog_id, dataset_root, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name.strip(), catalog_id, str(dataset_root.resolve()), created_at, created_at),
            )
            for image in images:
                connection.execute(
                    """INSERT INTO images
                       (id, project_id, relative_path, image_path, label_path, width, height, sort_index, error_message)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (image["id"], project_id, image["relative_path"], str(Path(image["image_path"]).resolve()), str(Path(image["label_path"]).resolve()), image["width"], image["height"], image["sort_index"], image["error_message"]),
                )
                for annotation in image["annotations"]:
                    tokens = tuple(annotation["coordinates"])
                    connection.execute(
                        """INSERT INTO annotations
                           (id, image_id, line_index, source_class_id, source_class_name, current_class_id, x_center, y_center, width, height, coordinate_tokens, original_line)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (annotation["id"], image["id"], annotation["line_index"], annotation["source_class_id"], annotation.get("source_class_name", f"Unknown source class {annotation['source_class_id']}"), annotation["current_class_id"], *(float(token) for token in tokens), json.dumps(tokens), annotation["original_line"]),
                    )
            connection.executemany(
                "INSERT INTO import_problems (project_id, relative_path, line_index, message) VALUES (?, ?, ?, ?)",
                ((project_id, problem["relative_path"], problem.get("line_index"), problem["message"]) for problem in problems),
            )

    def _summary(self, row) -> ProjectSummary:
        return ProjectSummary(row["id"], row["name"], row["catalog_id"], Path(row["dataset_root"]), row["created_at"], row["updated_at"], row["image_count"], row["annotation_count"], row["reviewed_count"], row["thumbnail_image_id"])

    def list(self, query: str = "", limit: int = 100, offset: int = 0) -> tuple[ProjectSummary, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT p.*,
                          COUNT(DISTINCT i.id) AS image_count,
                          COUNT(a.id) AS annotation_count,
                          COUNT(CASE WHEN a.decision IS NOT NULL THEN 1 END) AS reviewed_count,
                          (SELECT i2.id FROM images i2 WHERE i2.project_id = p.id ORDER BY i2.sort_index LIMIT 1) AS thumbnail_image_id
                   FROM projects p
                   LEFT JOIN images i ON i.project_id = p.id
                   LEFT JOIN annotations a ON a.image_id = i.id
                   WHERE p.name LIKE ? COLLATE NOCASE
                   GROUP BY p.id ORDER BY p.updated_at DESC, p.id LIMIT ? OFFSET ?""",
                (f"%{query.strip()}%", limit, offset),
            ).fetchall()
        return tuple(self._summary(row) for row in rows)

    def get(self, project_id: str) -> ProjectSummary:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT p.*, COUNT(DISTINCT i.id) AS image_count, COUNT(a.id) AS annotation_count,
                          COUNT(CASE WHEN a.decision IS NOT NULL THEN 1 END) AS reviewed_count,
                          (SELECT i2.id FROM images i2 WHERE i2.project_id = p.id ORDER BY i2.sort_index LIMIT 1) AS thumbnail_image_id
                   FROM projects p LEFT JOIN images i ON i.project_id = p.id
                   LEFT JOIN annotations a ON a.image_id = i.id WHERE p.id = ? GROUP BY p.id""",
                (project_id,),
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        return self._summary(row)

    @staticmethod
    def _image_summary(row) -> ImageSummary:
        return ImageSummary(row["id"], row["project_id"], row["relative_path"], Path(row["image_path"]), Path(row["label_path"]), row["width"], row["height"], row["sort_index"], row["error_message"], row["annotation_count"], row["reviewed_count"])

    def list_images(self, project_id: str, limit: int = 100, offset: int = 0) -> tuple[ImageSummary, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT i.*, COUNT(a.id) AS annotation_count,
                          COUNT(CASE WHEN a.decision IS NOT NULL THEN 1 END) AS reviewed_count
                   FROM images i LEFT JOIN annotations a ON a.image_id = i.id
                   WHERE i.project_id = ? GROUP BY i.id ORDER BY i.sort_index LIMIT ? OFFSET ?""",
                (project_id, limit, offset),
            ).fetchall()
        return tuple(self._image_summary(row) for row in rows)

    def get_image(self, project_id: str, image_id: str) -> ImageSummary:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT i.*, COUNT(a.id) AS annotation_count,
                          COUNT(CASE WHEN a.decision IS NOT NULL THEN 1 END) AS reviewed_count
                   FROM images i LEFT JOIN annotations a ON a.image_id = i.id
                   WHERE i.project_id = ? AND i.id = ? GROUP BY i.id""",
                (project_id, image_id),
            ).fetchone()
        if row is None:
            raise KeyError(image_id)
        return self._image_summary(row)

    def get_image_by_id(self, image_id: str) -> ImageSummary:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT i.*, COUNT(a.id) AS annotation_count,
                          COUNT(CASE WHEN a.decision IS NOT NULL THEN 1 END) AS reviewed_count
                   FROM images i LEFT JOIN annotations a ON a.image_id = i.id
                   WHERE i.id = ? GROUP BY i.id""",
                (image_id,),
            ).fetchone()
        if row is None:
            raise KeyError(image_id)
        return self._image_summary(row)

    def list_annotations(self, image_id: str) -> tuple[ImageAnnotation, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM annotations WHERE image_id = ? ORDER BY line_index",
                (image_id,),
            ).fetchall()
        return tuple(ImageAnnotation(row["id"], row["line_index"], row["source_class_id"], row["source_class_name"], row["current_class_id"], row["x_center"], row["y_center"], row["width"], row["height"], row["decision"], row["annotator_name"], row["version"]) for row in rows)

    def list_problems(self, project_id: str, relative_path: str | None = None) -> tuple[dict, ...]:
        sql = "SELECT relative_path, line_index, message FROM import_problems WHERE project_id = ?"
        arguments: tuple = (project_id,)
        if relative_path is not None:
            sql += " AND relative_path = ?"
            arguments = (project_id, relative_path)
        sql += " ORDER BY relative_path, line_index"
        with self.database.connect() as connection:
            rows = connection.execute(sql, arguments).fetchall()
        return tuple(dict(row) for row in rows)
