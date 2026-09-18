from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    assignments: Path
    projects: Path
    database: Path
    staging: Path

    @classmethod
    def from_root(cls, root: Path) -> "AppPaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            assignments=resolved / "assignments",
            projects=resolved / "projects",
            database=resolved / "progress.sqlite3",
            staging=resolved / "staging",
        )

    def ensure(self) -> None:
        self.assignments.mkdir(parents=True, exist_ok=True)
        self.projects.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ImportLimits:
    max_files: int = 25_000
    max_uncompressed_bytes: int = 20 * 1024**3
