from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

from annotate_tool.repositories.annotations import AnnotationRepository
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.repositories.projects import ProjectRepository
from annotate_tool.yolo import replace_class_token


@dataclass(frozen=True)
class ExportArchive:
    filename: str
    content: bytes


class ExportService:
    def __init__(self, projects: ProjectRepository, catalogs: CatalogRepository, annotations: AnnotationRepository):
        self.projects = projects
        self.catalogs = catalogs
        self.annotations = annotations

    def build(self, project_id: str) -> ExportArchive:
        try:
            project = self.projects.get(project_id)
        except KeyError as exc:
            raise LookupError("Project not found") from exc
        dataset_root = project.dataset_root.resolve()
        labels_root = dataset_root / "labels"
        backup_root = dataset_root / "backups" / "labels_original"
        allowed_ids = {item.class_id for item in self.catalogs.list_classes(project.catalog_id, limit=100_000)}
        decisions_by_label: dict[Path, list[dict]] = {}
        for decision in self.annotations.list_export_decisions(project_id):
            label_path = Path(decision["label_path"]).resolve()
            try:
                relative = label_path.relative_to(labels_root.resolve())
            except ValueError as exc:
                raise ValueError("Project label path is outside its dataset") from exc
            decisions_by_label.setdefault(relative, []).append(decision)

        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            if backup_root.is_dir():
                for original_path in sorted(backup_root.rglob("*")):
                    if not original_path.is_file():
                        continue
                    relative = original_path.relative_to(backup_root)
                    with original_path.open("r", encoding="utf-8", newline="") as source:
                        content = source.read()
                    for decision in decisions_by_label.get(relative, []):
                        content = replace_class_token(
                            content,
                            decision["line_index"],
                            decision["original_line"],
                            decision["current_class_id"],
                            allowed_class_ids=allowed_ids,
                        )
                    archive.writestr(f"labels/{relative.as_posix()}", content.encode("utf-8"))
            for metadata_name in ("classes.txt", "data.yaml"):
                metadata = dataset_root / metadata_name
                if metadata.is_file():
                    archive.writestr(metadata_name, metadata.read_bytes())
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", project.name).strip("._") or project.id
        return ExportArchive(f"{safe_name}_corrected_labels.zip", output.getvalue())
