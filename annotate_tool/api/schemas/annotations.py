from typing import Literal

from pydantic import BaseModel, Field


class AnnotationUpdateRequest(BaseModel):
    action: Literal["correct", "relabel", "skip"]
    target_class_id: int | None = Field(default=None, ge=0)
    annotator_name: str | None = Field(default=None, max_length=200)


class AnnotationUpdateResponse(BaseModel):
    id: str
    image_id: str
    line_index: int
    source_class_id: int
    current_class_id: int
    decision: str
    annotator_name: str | None
    version: int
    updated_at: str
