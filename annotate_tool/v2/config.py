from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class V2Paths:
    root: Path
    database: Path
    staging: Path
    catalogs: Path
    projects: Path
    exports: Path

    @classmethod
    def from_root(cls, root: Path) -> "V2Paths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            database=resolved / "app.sqlite3",
            staging=resolved / "staging",
            catalogs=resolved / "catalogs",
            projects=resolved / "projects",
            exports=resolved / "exports",
        )

    def ensure(self) -> None:
        for directory in (self.root, self.staging, self.catalogs, self.projects, self.exports):
            directory.mkdir(parents=True, exist_ok=True)

