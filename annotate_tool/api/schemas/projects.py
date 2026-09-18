from pydantic import BaseModel


class ProjectResponse(BaseModel):
    id: str
    name: str
    catalog_id: str
    image_count: int
    annotation_count: int
    reviewed_count: int
    thumbnail_url: str | None
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    limit: int
    offset: int

