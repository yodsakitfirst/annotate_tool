from pydantic import BaseModel


class ImageSummaryResponse(BaseModel):
    id: str
    relative_path: str
    width: int | None
    height: int | None
    annotation_count: int
    reviewed_count: int
    error_message: str | None
    media_url: str


class ImageListResponse(BaseModel):
    items: list[ImageSummaryResponse]
    limit: int
    offset: int


class CoordinatesResponse(BaseModel):
    x_center: float
    y_center: float
    width: float
    height: float


class ImageAnnotationResponse(BaseModel):
    id: str
    line_index: int
    source_class_id: int
    source_class_name: str
    current_class_id: int
    coordinates: CoordinatesResponse
    decision: str | None
    annotator_name: str | None
    version: int


class ImageDetailResponse(ImageSummaryResponse):
    annotations: list[ImageAnnotationResponse]
    problems: list[dict]

