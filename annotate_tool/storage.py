from dataclasses import asdict, dataclass
from io import BytesIO, StringIO
import csv
from collections.abc import Collection
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from annotate_tool.progress import ProgressRepository
from annotate_tool.yolo import replace_class_token


@dataclass(frozen=True)
class ExportResult:
    filename: str
    content: bytes


def atomic_relabel(
    label_path: Path,
    line_index: int,
    expected_line: str,
    new_class_id: int,
    allowed_class_ids: Collection[int] | None = None,
) -> None:
    with label_path.open("r", encoding="utf-8", newline="") as source:
        original = source.read()
    updated = replace_class_token(
        original,
        line_index,
        expected_line,
        new_class_id,
        allowed_class_ids=allowed_class_ids,
    )
    original_mode = label_path.stat().st_mode
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{label_path.name}.",
            suffix=".tmp",
            dir=label_path.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, label_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _progress_json(assignment_id: str, repository: ProgressRepository) -> bytes:
    payload = {
        "assignment_id": assignment_id,
        "summary": repository.summary(assignment_id),
        "decisions": [asdict(decision) for decision in repository.list_decisions(assignment_id)],
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _problems_csv(assignment_id: str, repository: ProgressRepository) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("path", "message"))
    writer.writerows(repository.list_problems(assignment_id))
    return output.getvalue().encode("utf-8-sig")


def build_export(
    assignment_id: str,
    assignment_root: Path,
    repository: ProgressRepository,
) -> ExportResult:
    root = assignment_root.resolve()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        labels = root / "labels"
        if labels.is_dir():
            for path in sorted(labels.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())

        metadata = root / "data.yaml"
        if not metadata.is_file():
            metadata = root / "classes.txt"
        if metadata.is_file():
            archive.write(metadata, metadata.name)

        archive.writestr("progress.json", _progress_json(assignment_id, repository))
        archive.writestr("problems.csv", _problems_csv(assignment_id, repository))

    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", assignment_id).strip("._") or "assignment"
    return ExportResult(f"{safe_id}_corrected_labels.zip", output.getvalue())
