from dataclasses import dataclass

from annotate_tool.v2.database import Database


@dataclass(frozen=True)
class AnnotationRecord:
    id: str
    image_id: str
    project_id: str
    catalog_id: str
    line_index: int
    source_class_id: int
    current_class_id: int
    decision: str | None
    annotator_name: str | None
    version: int
    updated_at: str | None


class AnnotationRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _record(row) -> AnnotationRecord:
        return AnnotationRecord(row["id"], row["image_id"], row["project_id"], row["catalog_id"], row["line_index"], row["source_class_id"], row["current_class_id"], row["decision"], row["annotator_name"], row["version"], row["updated_at"])

    def get(self, annotation_id: str, connection=None) -> AnnotationRecord:
        owns_connection = connection is None
        connection = connection or self.database.connect()
        try:
            row = connection.execute(
                """SELECT a.*, i.project_id, p.catalog_id
                   FROM annotations a JOIN images i ON i.id = a.image_id
                   JOIN projects p ON p.id = i.project_id WHERE a.id = ?""",
                (annotation_id,),
            ).fetchone()
        finally:
            if owns_connection:
                connection.close()
        if row is None:
            raise KeyError(annotation_id)
        return self._record(row)

    def update_decision(self, annotation_id: str, *, decision: str, target_class_id: int | None, annotator_name: str | None, updated_at: str) -> AnnotationRecord:
        if decision not in {"correct", "relabel", "skip"}:
            raise ValueError("invalid annotation decision")
        with self.database.transaction(immediate=True) as connection:
            current = self.get(annotation_id, connection)
            resulting_class = target_class_id if decision == "relabel" else current.current_class_id
            connection.execute(
                """UPDATE annotations SET decision = ?, current_class_id = ?, annotator_name = ?,
                   version = version + 1, updated_at = ? WHERE id = ?""",
                (decision, resulting_class, annotator_name or None, updated_at, annotation_id),
            )
            connection.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (updated_at, current.project_id))
            return self.get(annotation_id, connection)

    def list_export_decisions(self, project_id: str) -> tuple[dict, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT i.label_path, a.line_index, a.source_class_id, a.current_class_id,
                          a.original_line, a.decision
                   FROM annotations a JOIN images i ON i.id = a.image_id
                   WHERE i.project_id = ? AND a.decision = 'relabel'
                   ORDER BY i.sort_index, a.line_index""",
                (project_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
