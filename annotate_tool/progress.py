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
class ReviewDecision:
    assignment_id: str
    image_path: str
    line_index: int
    decision: DecisionKind
    previous_class_id: int
    resulting_class_id: int | None
    decided_at: str


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

    def register_assignment(self, assignment_id: str, display_name: str, root: Path) -> None:
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO assignments (assignment_id, display_name, root, imported_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(assignment_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    root=excluded.root
                """,
                (assignment_id, display_name, str(root.resolve()), imported_at),
            )

    def list_assignments(self) -> tuple[AssignmentRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT assignment_id, display_name, root, imported_at "
                "FROM assignments ORDER BY imported_at DESC, assignment_id DESC"
            ).fetchall()
        return tuple(
            AssignmentRecord(row["assignment_id"], row["display_name"], Path(row["root"]), row["imported_at"])
            for row in rows
        )

    def record_decision(
        self,
        assignment_id: str,
        image_path: str,
        line_index: int,
        decision: DecisionKind,
        previous_class_id: int,
        resulting_class_id: int | None,
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
                        previous_class_id, resulting_class_id, decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(assignment_id, image_path, line_index) DO UPDATE SET
                        decision=excluded.decision,
                        previous_class_id=excluded.previous_class_id,
                        resulting_class_id=excluded.resulting_class_id,
                        decided_at=excluded.decided_at
                    """,
                    (
                        assignment_id,
                        image_path,
                        line_index,
                        decision,
                        previous_class_id,
                        resulting_class_id,
                        decided_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"decision requires a registered assignment: {assignment_id}") from exc

    def list_decisions(self, assignment_id: str) -> tuple[ReviewDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT assignment_id, image_path, line_index, decision,
                       previous_class_id, resulting_class_id, decided_at
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
