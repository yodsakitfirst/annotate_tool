from datetime import datetime, timezone

from annotate_tool.repositories.annotations import AnnotationRecord, AnnotationRepository
from annotate_tool.repositories.catalogs import CatalogRepository


class AnnotationNotFoundError(LookupError):
    pass


class InvalidTargetClassError(ValueError):
    pass


class AnnotationService:
    def __init__(self, annotations: AnnotationRepository, catalogs: CatalogRepository):
        self.annotations = annotations
        self.catalogs = catalogs

    def update(self, annotation_id: str, *, action: str, target_class_id: int | None, annotator_name: str | None) -> AnnotationRecord:
        try:
            current = self.annotations.get(annotation_id)
        except KeyError as exc:
            raise AnnotationNotFoundError("Annotation not found") from exc
        if action == "relabel":
            if target_class_id is None or not self.catalogs.has_class(current.catalog_id, target_class_id):
                raise InvalidTargetClassError("Target class is not in the project's catalog")
        elif action == "correct":
            if target_class_id is not None:
                raise InvalidTargetClassError("Correct does not accept a target class")
            if not self.catalogs.has_class(current.catalog_id, current.current_class_id):
                raise InvalidTargetClassError("Current class is not in the project's catalog")
        elif action == "skip":
            if target_class_id is not None:
                raise InvalidTargetClassError("Skip does not accept a target class")
        else:
            raise ValueError("Invalid annotation action")
        updated_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        return self.annotations.update_decision(
            annotation_id,
            decision=action,
            target_class_id=target_class_id,
            annotator_name=(annotator_name or "").strip() or None,
            updated_at=updated_at,
        )
