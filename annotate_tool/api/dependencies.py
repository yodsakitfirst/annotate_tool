from dataclasses import dataclass, field
import os
from pathlib import Path

from fastapi import Request

from annotate_tool.config import ImportLimits
from annotate_tool.repositories.annotations import AnnotationRepository
from annotate_tool.repositories.catalogs import CatalogRepository
from annotate_tool.repositories.projects import ProjectRepository
from annotate_tool.services.catalog_service import CatalogService
from annotate_tool.services.annotation_service import AnnotationService
from annotate_tool.services.export_service import ExportService
from annotate_tool.services.project_service import ProjectService
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.database import Database


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("ANNOTATE_TOOL_DATA_DIR", "workspace_v2"))
    )
    frontend_dist: Path = field(
        default_factory=lambda: Path(os.environ.get("ANNOTATE_TOOL_FRONTEND_DIST", "frontend/dist"))
    )
    import_limits: ImportLimits = field(default_factory=ImportLimits)
    max_upload_bytes: int = 4 * 1024**3


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    paths: V2Paths
    database: Database
    catalogs: CatalogRepository
    projects: ProjectRepository
    annotations: AnnotationRepository
    catalog_service: CatalogService
    project_service: ProjectService
    annotation_service: AnnotationService
    export_service: ExportService


def build_context(settings: Settings) -> AppContext:
    paths = V2Paths.from_root(settings.data_dir)
    database = Database(paths.database)
    catalogs = CatalogRepository(database)
    projects = ProjectRepository(database)
    return AppContext(
        settings=settings,
        paths=paths,
        database=database,
        catalogs=catalogs,
        projects=projects,
        annotations=AnnotationRepository(database),
        catalog_service=CatalogService(paths, catalogs, settings.import_limits),
        project_service=ProjectService(paths, catalogs, projects, settings.import_limits),
        annotation_service=AnnotationService(AnnotationRepository(database), catalogs),
        export_service=ExportService(projects, catalogs, AnnotationRepository(database)),
    )


def get_context(request: Request) -> AppContext:
    return request.app.state.context
