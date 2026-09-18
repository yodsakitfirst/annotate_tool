import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError


router = APIRouter()


def confined_file(path: Path, root: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ApiError(404, "media_not_found", "Media not found") from exc
    if not resolved.is_file():
        raise ApiError(404, "media_not_found", "Media not found")
    return resolved


@router.get("/media/catalogs/{catalog_id}/classes/{class_id}")
def catalog_image(catalog_id: str, class_id: int, context: AppContext = Depends(get_context)):
    try:
        record = context.catalogs.get_class(catalog_id, class_id)
    except KeyError as exc:
        raise ApiError(404, "media_not_found", "Media not found") from exc
    path = confined_file(record.reference_path, context.paths.root)
    stat = path.stat()
    etag = hashlib.sha256(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600", "ETag": f'"{etag}"'})


@router.get("/media/images/{image_id}")
def project_image(image_id: str, context: AppContext = Depends(get_context)):
    try:
        record = context.projects.get_image_by_id(image_id)
    except KeyError as exc:
        raise ApiError(404, "media_not_found", "Media not found") from exc
    path = confined_file(record.image_path, context.paths.root)
    stat = path.stat()
    etag = hashlib.sha256(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600", "ETag": f'"{etag}"'})
