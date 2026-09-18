from fastapi import APIRouter, Depends
from fastapi.responses import Response

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError


router = APIRouter()


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, context: AppContext = Depends(get_context)):
    try:
        archive = context.export_service.build(project_id)
    except LookupError as exc:
        raise ApiError(404, "project_not_found", "Project not found") from exc
    return Response(
        archive.content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive.filename}"'},
    )
