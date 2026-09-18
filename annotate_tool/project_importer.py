from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from annotate_tool.config import AppPaths, ImportLimits
from annotate_tool.importer import AssignmentImportError, import_dataset
from annotate_tool.models import ClassInfo
from annotate_tool.reference_catalog import ReferenceCatalogError, import_reference_catalog


@dataclass(frozen=True)
class ImportedProject:
    project_id: str
    display_name: str
    owner_name: str
    dataset_root: Path
    reference_root: Path
    reference_classes: tuple[ClassInfo, ...]


class ProjectImportError(ValueError):
    pass


def import_project(
    dataset_zip: Path,
    catalog_zip: Path,
    display_name: str,
    owner_name: str,
    paths: AppPaths,
    limits: ImportLimits,
) -> ImportedProject:
    cleaned_name = display_name.strip()
    cleaned_owner = owner_name.strip()
    if not cleaned_name:
        raise ProjectImportError("project display name is required")
    if not cleaned_owner:
        raise ProjectImportError("project owner name is required")
    paths.ensure()
    project_id = uuid.uuid4().hex
    project_root = paths.projects / project_id
    dataset_root = project_root / "dataset"
    reference_root = project_root / "references"
    project_root.mkdir()
    complete = False
    try:
        import_dataset(dataset_zip, cleaned_name, dataset_root, limits)
        reference_classes = import_reference_catalog(catalog_zip, reference_root, limits)
        complete = True
        return ImportedProject(
            project_id=project_id,
            display_name=cleaned_name,
            owner_name=cleaned_owner,
            dataset_root=dataset_root,
            reference_root=reference_root,
            reference_classes=reference_classes,
        )
    except (AssignmentImportError, ReferenceCatalogError, OSError) as exc:
        raise ProjectImportError(str(exc)) from exc
    finally:
        if not complete and project_root.exists():
            shutil.rmtree(project_root)
