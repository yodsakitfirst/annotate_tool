import logging
import sqlite3

from fastapi import APIRouter, Depends

from annotate_tool.api.dependencies import AppContext, get_context
from annotate_tool.api.errors import ApiError
from annotate_tool.api.schemas.annotations import AnnotationUpdateRequest, AnnotationUpdateResponse
from annotate_tool.services.annotation_service import AnnotationNotFoundError, InvalidTargetClassError


router = APIRouter()
logger = logging.getLogger("annotate_tool")


@router.patch("/annotations/{annotation_id}", response_model=AnnotationUpdateResponse)
def update_annotation(annotation_id: str, payload: AnnotationUpdateRequest, context: AppContext = Depends(get_context)):
    try:
        item = context.annotation_service.update(
            annotation_id,
            action=payload.action,
            target_class_id=payload.target_class_id,
            annotator_name=payload.annotator_name,
        )
    except AnnotationNotFoundError as exc:
        raise ApiError(404, "annotation_not_found", "Annotation not found") from exc
    except InvalidTargetClassError as exc:
        raise ApiError(422, "target_class_invalid", str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        logger.exception("Annotation write failed")
        raise ApiError(
            503, "annotation_write_failed", "Annotation could not be saved"
        ) from exc
    return AnnotationUpdateResponse(
        id=item.id, image_id=item.image_id, line_index=item.line_index,
        source_class_id=item.source_class_id, current_class_id=item.current_class_id,
        decision=item.decision or payload.action, annotator_name=item.annotator_name,
        version=item.version, updated_at=item.updated_at or "",
    )
