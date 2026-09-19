from dataclasses import dataclass
import os
from pathlib import Path
import uuid


class StorageValidationError(RuntimeError):
    pass


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

    def validate_writable(self) -> None:
        self.ensure()
        for directory in (
            self.root,
            self.staging,
            self.catalogs,
            self.projects,
            self.exports,
        ):
            probe = directory / f".write-probe-{uuid.uuid4().hex}"
            try:
                with probe.open("xb") as handle:
                    handle.write(b"ok")
                    handle.flush()
                    os.fsync(handle.fileno())
                probe.unlink()
            except OSError as exc:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass
                raise StorageValidationError("Persistent storage is not writable") from exc

