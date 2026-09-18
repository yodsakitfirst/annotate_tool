from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator, Literal


DecisionKind = Literal["correct", "relabel", "skip"]


@dataclass(frozen=True)
class AssignmentRecord:
    assignment_id: str
    display_name: str
    root: Path
    imported_at: str


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    display_name: str
    dataset_root: Path
    reference_root: Path | None
    owner_name: str | None
    imported_at: str


@dataclass(frozen=True)
class ReviewDecision:
    assignment_id: str
    image_path: str
    line_index: int
    decision: DecisionKind
    previous_class_id: int
    resulting_class_id: int | None
    decided_at: str
    annotator_name: str | None = None


class ProgressRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    root TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    assignment_id TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    line_index INTEGER NOT NULL CHECK (line_index >= 0),
                    decision TEXT NOT NULL CHECK (decision IN ('correct', 'relabel', 'skip')),
                    previous_class_id INTEGER NOT NULL,
                    resulting_class_id INTEGER,
                    decided_at TEXT NOT NULL,
                    PRIMARY KEY (assignment_id, image_path, line_index),
                    FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS problems (
                    assignment_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (assignment_id, path, message),
                    FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
                );
                """
            )
            assignment_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(assignments)")
            }
            if "dataset_root" not in assignment_columns:
                connection.execute("ALTER TABLE assignments ADD COLUMN dataset_root TEXT")
            if "reference_root" not in assignment_columns:
                connection.execute("ALTER TABLE assignments ADD COLUMN reference_root TEXT")
            if "owner_name" not in assignment_columns:
                connection.execute("ALTER TABLE assignments ADD COLUMN owner_name TEXT")
            connection.execute(
                "UPDATE assignments SET dataset_root = root WHERE dataset_root IS NULL"
            )

            decision_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(decisions)")
            }
            if "annotator_name" not in decision_columns:
                connection.execute("ALTER TABLE decisions ADD COLUMN annotator_name TEXT")

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reference_classes (
                    assignment_id TEXT NOT NULL,
                    class_id INTEGER NOT NULL CHECK (class_id >= 0),
                    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
                    image_path TEXT NOT NULL,
                    display_order INTEGER NOT NULL CHECK (display_order >= 0),
                    PRIMARY KEY (assignment_id, class_id),
                    FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id) ON DELETE CASCADE
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (1, datetime.now(timezone.utc).isoformat(timespec="microseconds")),
            )

    def register_project(
        self,
        project_id: str,
        display_name: str,
        dataset_root: Path,
        reference_root: Path | None,
        owner_name: str | None = None,
    ) -> None:
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        normalized_owner = owner_name.strip() if owner_name is not None else None
        if owner_name is not None and not normalized_owner:
            raise ValueError("project owner name is required")
        resolved_dataset = dataset_root.resolve()
        resolved_references = reference_root.resolve() if reference_root is not None else None
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assignments (
                    assignment_id, display_name, root, imported_at,
                    dataset_root, reference_root, owner_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(assignment_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    root=excluded.root,
                    dataset_root=excluded.dataset_root,
                    reference_root=excluded.reference_root,
                    owner_name=COALESCE(excluded.owner_name, assignments.owner_name)
                """,
                (
                    project_id,
                    display_name.strip(),
                    str(resolved_dataset),
                    imported_at,
                    str(resolved_dataset),
                    str(resolved_references) if resolved_references is not None else None,
                    normalized_owner,
                ),
            )

    def assign_project(self, project_id: str, owner_name: str) -> None:
        normalized_owner = owner_name.strip()
        if not normalized_owner:
            raise ValueError("project owner name is required")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE assignments SET owner_name = ? WHERE assignment_id = ?",
                (normalized_owner, project_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown project: {project_id}")

    def get_project(self, project_id: str) -> ProjectRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT assignment_id, display_name, COALESCE(dataset_root, root) AS dataset_root,
                       reference_root, owner_name, imported_at
                FROM assignments WHERE assignment_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown project: {project_id}")
        return ProjectRecord(
            project_id=row["assignment_id"],
            display_name=row["display_name"],
            dataset_root=Path(row["dataset_root"]),
            reference_root=Path(row["reference_root"]) if row["reference_root"] else None,
            owner_name=row["owner_name"],
            imported_at=row["imported_at"],
        )

    def list_projects(self) -> tuple[ProjectRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT assignment_id, display_name, COALESCE(dataset_root, root) AS dataset_root,
                       reference_root, owner_name, imported_at
                FROM assignments ORDER BY imported_at DESC, assignment_id DESC
                """
            ).fetchall()
        return tuple(
            ProjectRecord(
                project_id=row["assignment_id"],
                display_name=row["display_name"],
                dataset_root=Path(row["dataset_root"]),
                reference_root=Path(row["reference_root"]) if row["reference_root"] else None,
                owner_name=row["owner_name"],
                imported_at=row["imported_at"],
            )
            for row in rows
        )

    def can_edit_project(self, project_id: str, annotator_name: str) -> bool:
        project = self.get_project(project_id)
        return bool(project.owner_name) and project.owner_name == annotator_name.strip()

    def register_assignment(self, assignment_id: str, display_name: str, root: Path) -> None:
        self.register_project(assignment_id, display_name, root, None)

    def list_assignments(self) -> tuple[AssignmentRecord, ...]:
        return tuple(
            AssignmentRecord(project.project_id, project.display_name, project.dataset_root, project.imported_at)
            for project in self.list_projects()
        )

    def record_decision(
        self,
        assignment_id: str,
        image_path: str,
        line_index: int,
        decision: DecisionKind,
        previous_class_id: int,
        resulting_class_id: int | None,
        annotator_name: str | None = None,
    ) -> None:
        if decision not in {"correct", "relabel", "skip"}:
            raise ValueError(f"unsupported review decision: {decision}")
        decided_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO decisions (
                        assignment_id, image_path, line_index, decision,
                        previous_class_id, resulting_class_id, decided_at, annotator_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(assignment_id, image_path, line_index) DO UPDATE SET
                        decision=excluded.decision,
                        previous_class_id=excluded.previous_class_id,
                        resulting_class_id=excluded.resulting_class_id,
                        decided_at=excluded.decided_at,
                        annotator_name=excluded.annotator_name
                    """,
                    (
                        assignment_id,
                        image_path,
                        line_index,
                        decision,
                        previous_class_id,
                        resulting_class_id,
                        decided_at,
                        annotator_name.strip() if annotator_name else None,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"decision requires a registered assignment: {assignment_id}") from exc

    def list_decisions(self, assignment_id: str) -> tuple[ReviewDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT assignment_id, image_path, line_index, decision,
                       previous_class_id, resulting_class_id, decided_at, annotator_name
                FROM decisions
                WHERE assignment_id = ?
                ORDER BY image_path, line_index
                """,
                (assignment_id,),
            ).fetchall()
        return tuple(
            ReviewDecision(
                assignment_id=row["assignment_id"],
                image_path=row["image_path"],
                line_index=row["line_index"],
                decision=row["decision"],
                previous_class_id=row["previous_class_id"],
                resulting_class_id=row["resulting_class_id"],
                decided_at=row["decided_at"],
                annotator_name=row["annotator_name"],
            )
            for row in rows
        )

    def reviewed_keys(self, assignment_id: str) -> set[tuple[str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT image_path, line_index FROM decisions
                WHERE assignment_id = ? AND decision IN ('correct', 'relabel')
                """,
                (assignment_id,),
            ).fetchall()
        return {(row["image_path"], row["line_index"]) for row in rows}

    def summary(self, assignment_id: str) -> dict[str, int]:
        counts = {"correct": 0, "relabel": 0, "skipped": 0}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision, COUNT(*) AS count FROM decisions "
                "WHERE assignment_id = ? GROUP BY decision",
                (assignment_id,),
            ).fetchall()
        for row in rows:
            key = "skipped" if row["decision"] == "skip" else row["decision"]
            counts[key] = row["count"]
        return {
            "reviewed": counts["correct"] + counts["relabel"],
            "correct": counts["correct"],
            "relabel": counts["relabel"],
            "skipped": counts["skipped"],
        }

    def record_problem(self, assignment_id: str, path: str, message: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO problems (assignment_id, path, message, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (assignment_id, path, message, created_at),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"problem requires a registered assignment: {assignment_id}") from exc

    def list_problems(self, assignment_id: str) -> tuple[tuple[str, str], ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT path, message FROM problems WHERE assignment_id = ? ORDER BY path, message",
                (assignment_id,),
            ).fetchall()
        return tuple((row["path"], row["message"]) for row in rows)
