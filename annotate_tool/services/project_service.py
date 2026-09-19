from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from annotate_tool.config import ImportLimits
from annotate_tool.dataset import (
    DatasetLoadError,
    DatasetStorageError,
    load_assignment,
    source_class_name,
)
from annotate_tool.importer import AssignmentImportError, AssignmentStorageError, import_dataset
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.repositories.projects import ProjectRepository, ProjectSummary
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.filesystem import publish_directory


class ProjectImportError(ValueError):
    pass


class ProjectStorageError(RuntimeError):
    pass


class ProjectService:
    def __init__(self, paths: V2Paths, catalogs: CatalogRepository, projects: ProjectRepository, limits: ImportLimits):
        self.paths = paths
        self.catalogs = catalogs
        self.projects = projects
        self.limits = limits

    def import_project(self, name: str, catalog_id: str, zip_path: Path) -> ProjectSummary:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ProjectImportError("Project name is required")
        try:
            self.catalogs.get(catalog_id)
        except KeyError as exc:
            raise LookupError("Catalog not found") from exc
        project_id = uuid.uuid4().hex
        staged_root = self.paths.staging / f"project-{project_id}"
        staged_dataset = staged_root / "dataset"
        final_root = self.paths.projects / project_id
        final_dataset = final_root / "dataset"
        published = False
        try:
            import_dataset(zip_path, cleaned_name, staged_dataset, self.limits)
            dataset = load_assignment(staged_dataset)
            images: list[dict] = []
            for sort_index, image in enumerate(dataset.images):
                image_id = uuid.uuid5(uuid.UUID(project_id), image.relative_path).hex
                relative_image_path = image.path.relative_to(staged_dataset)
                relative_label_path = image.label_path.relative_to(staged_dataset)
                images.append(
                    {
                        "id": image_id,
                        "relative_path": image.relative_path,
                        "image_path": final_dataset / relative_image_path,
                        "label_path": final_dataset / relative_label_path,
                        "width": image.image_size[0] if image.image_size else None,
                        "height": image.image_size[1] if image.image_size else None,
                        "sort_index": sort_index,
                        "error_message": image.image_error,
                        "annotations": tuple(
                            {
                                "id": uuid.uuid5(uuid.UUID(image_id), str(annotation.line_index)).hex,
                                "line_index": annotation.line_index,
                                "source_class_id": annotation.class_id,
                                "source_class_name": source_class_name(dataset, annotation.class_id),
                                "current_class_id": annotation.class_id,
                                "coordinates": annotation.coordinate_tokens,
                                "original_line": annotation.original_line,
                            }
                            for annotation in image.parse_result.annotations
                        ),
                    }
                )
            problems = tuple(
                {
                    "relative_path": self._relative_problem_path(problem.path, staged_dataset),
                    "line_index": problem.line_index,
                    "message": problem.message,
                }
                for problem in dataset.problems
            )
            (staged_root / ".complete").write_text("complete\n", encoding="utf-8")
            publish_directory(staged_root, final_root, self.paths.staging, self.paths.projects)
            published = True
            created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            self.projects.create(
                project_id=project_id,
                name=cleaned_name,
                catalog_id=catalog_id,
                dataset_root=final_dataset,
                created_at=created_at,
                images=tuple(images),
                problems=problems,
            )
            return self.projects.get(project_id)
        except (AssignmentStorageError, DatasetStorageError) as exc:
            raise ProjectStorageError("Project storage operation failed") from exc
        except (AssignmentImportError, DatasetLoadError) as exc:
            raise ProjectImportError(str(exc)) from exc
        except OSError as exc:
            raise ProjectStorageError("Project storage operation failed") from exc
        finally:
            if staged_root.exists():
                shutil.rmtree(staged_root)
            if published:
                try:
                    self.projects.get(project_id)
                except KeyError:
                    if final_root.exists():
                        shutil.rmtree(final_root)

    @staticmethod
    def _relative_problem_path(path: Path | None, dataset_root: Path) -> str:
        if path is None:
            return "dataset"
        try:
            return path.resolve().relative_to(dataset_root.resolve()).as_posix()
        except ValueError:
            return path.name
