import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError
from annotate_tool.api.routes.catalogs import save_upload
from annotate_tool.api.schemas.projects import ProjectListResponse, ProjectResponse
from annotate_tool.repositories.projects import ProjectSummary
from annotate_tool.services.project_service import ProjectImportError, ProjectStorageError


router = APIRouter()
logger = logging.getLogger("annotate_tool")


def project_response(item: ProjectSummary) -> ProjectResponse:
    return ProjectResponse(
        id=item.id, name=item.name, catalog_id=item.catalog_id,
        image_count=item.image_count, annotation_count=item.annotation_count,
        reviewed_count=item.reviewed_count,
        thumbnail_url=f"/media/images/{item.thumbnail_image_id}" if item.thumbnail_image_id else None,
        created_at=item.created_at, updated_at=item.updated_at,
    )


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(query: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), context: AppContext = Depends(get_context)):
    return ProjectListResponse(items=[project_response(item) for item in context.projects.list(query, limit, offset)], limit=limit, offset=offset)


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(name: str = Form(...), catalog_id: str = Form(...), dataset_zip: UploadFile = File(...), context: AppContext = Depends(get_context)):
    upload_path = context.paths.staging / f"upload-{uuid.uuid4().hex}.zip"
    try:
        save_upload(dataset_zip, upload_path, context.settings.max_upload_bytes)
        try:
            return project_response(context.project_service.import_project(name, catalog_id, upload_path))
        except LookupError as exc:
            raise ApiError(404, "catalog_not_found", "Catalog not found") from exc
        except ProjectImportError as exc:
            logger.warning("Project import rejected")
            raise ApiError(422, "project_invalid", str(exc)) from exc
        except ProjectStorageError as exc:
            logger.exception("Project import storage failure")
            raise ApiError(
                503, "storage_unavailable", "Project storage is unavailable"
            ) from exc
    except OSError as exc:
        logger.exception("Project upload storage failure")
        raise ApiError(
            503, "storage_unavailable", "Project storage is unavailable"
        ) from exc
    finally:
        upload_path.unlink(missing_ok=True)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, context: AppContext = Depends(get_context)):
    try:
        return project_response(context.projects.get(project_id))
    except KeyError as exc:
        raise ApiError(404, "project_not_found", "Project not found") from exc

