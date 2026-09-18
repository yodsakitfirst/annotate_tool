from fastapi import APIRouter, Depends, Query

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError
from annotate_tool.api.schemas.images import (
    CoordinatesResponse,
    ImageAnnotationResponse,
    ImageDetailResponse,
    ImageListResponse,
    ImageSummaryResponse,
)


router = APIRouter()


def image_summary(item) -> ImageSummaryResponse:
    return ImageSummaryResponse(id=item.id, relative_path=item.relative_path, width=item.width, height=item.height, annotation_count=item.annotation_count, reviewed_count=item.reviewed_count, error_message=item.error_message, media_url=f"/media/images/{item.id}")


@router.get("/projects/{project_id}/images", response_model=ImageListResponse)
def list_images(project_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), context: AppContext = Depends(get_context)):
    try:
        context.projects.get(project_id)
    except KeyError as exc:
        raise ApiError(404, "project_not_found", "Project not found") from exc
    return ImageListResponse(items=[image_summary(item) for item in context.projects.list_images(project_id, limit, offset)], limit=limit, offset=offset)


@router.get("/projects/{project_id}/images/{image_id}", response_model=ImageDetailResponse)
def get_image(project_id: str, image_id: str, context: AppContext = Depends(get_context)):
    try:
        item = context.projects.get_image(project_id, image_id)
    except KeyError as exc:
        raise ApiError(404, "image_not_found", "Image not found") from exc
    summary = image_summary(item).model_dump()
    annotations = [
        ImageAnnotationResponse(
            id=annotation.id, line_index=annotation.line_index,
            source_class_id=annotation.source_class_id, source_class_name=annotation.source_class_name,
            current_class_id=annotation.current_class_id,
            coordinates=CoordinatesResponse(x_center=annotation.x_center, y_center=annotation.y_center, width=annotation.width, height=annotation.height),
            decision=annotation.decision, annotator_name=annotation.annotator_name, version=annotation.version,
        )
        for annotation in context.projects.list_annotations(image_id)
    ]
    return ImageDetailResponse(**summary, annotations=annotations, problems=list(context.projects.list_problems(project_id, item.relative_path)))
