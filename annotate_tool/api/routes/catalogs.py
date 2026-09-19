import logging
from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError
from annotate_tool.api.schemas.catalogs import (
    CatalogClassListResponse,
    CatalogClassResponse,
    CatalogListResponse,
    CatalogResponse,
)
from annotate_tool.repositories.catalogs import CatalogRecord
from annotate_tool.services.catalog_service import CatalogImportError, CatalogStorageError


router = APIRouter()
logger = logging.getLogger("annotate_tool")


def catalog_response(record: CatalogRecord, context: AppContext) -> CatalogResponse:
    classes = context.catalogs.list_classes(record.id, limit=1)
    return CatalogResponse(
        id=record.id,
        name=record.name,
        class_count=record.class_count,
        created_at=record.created_at,
        preview_url=(f"/media/catalogs/{record.id}/classes/{classes[0].class_id}" if classes else None),
    )


def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    total = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ApiError(413, "upload_too_large", "Upload exceeds the configured size limit")
            output.write(chunk)


@router.get("/catalogs", response_model=CatalogListResponse)
def list_catalogs(query: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), context: AppContext = Depends(get_context)):
    return CatalogListResponse(items=[catalog_response(item, context) for item in context.catalogs.list(query, limit, offset)], limit=limit, offset=offset)


@router.post("/catalogs", response_model=CatalogResponse, status_code=status.HTTP_201_CREATED)
def create_catalog(name: str = Form(...), catalog_zip: UploadFile = File(...), context: AppContext = Depends(get_context)):
    upload_path = context.paths.staging / f"upload-{uuid.uuid4().hex}.zip"
    try:
        save_upload(catalog_zip, upload_path, context.settings.max_upload_bytes)
        try:
            record = context.catalog_service.import_catalog(name, upload_path)
        except CatalogImportError as exc:
            logger.warning("Catalog import rejected")
            raise ApiError(422, "catalog_invalid", str(exc)) from exc
        except CatalogStorageError as exc:
            logger.exception("Catalog import storage failure")
            raise ApiError(
                503, "storage_unavailable", "Catalog storage is unavailable"
            ) from exc
        return catalog_response(record, context)
    except OSError as exc:
        logger.exception("Catalog upload storage failure")
        raise ApiError(
            503, "storage_unavailable", "Catalog storage is unavailable"
        ) from exc
    finally:
        upload_path.unlink(missing_ok=True)


@router.get("/catalogs/{catalog_id}", response_model=CatalogResponse)
def get_catalog(catalog_id: str, context: AppContext = Depends(get_context)):
    try:
        return catalog_response(context.catalogs.get(catalog_id), context)
    except KeyError as exc:
        raise ApiError(404, "catalog_not_found", "Catalog not found") from exc


@router.get("/catalogs/{catalog_id}/classes", response_model=CatalogClassListResponse)
def list_catalog_classes(catalog_id: str, query: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), context: AppContext = Depends(get_context)):
    try:
        context.catalogs.get(catalog_id)
    except KeyError as exc:
        raise ApiError(404, "catalog_not_found", "Catalog not found") from exc
    items = context.catalogs.list_classes(catalog_id, query, limit, offset)
    return CatalogClassListResponse(
        items=[CatalogClassResponse(class_id=item.class_id, name=item.name, thumbnail_url=f"/media/catalogs/{catalog_id}/classes/{item.class_id}") for item in items],
        limit=limit,
        offset=offset,
    )

