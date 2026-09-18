from pydantic import BaseModel


class CatalogResponse(BaseModel):
    id: str
    name: str
    class_count: int
    created_at: str
    preview_url: str | None


class CatalogClassResponse(BaseModel):
    class_id: int
    name: str
    thumbnail_url: str


class CatalogListResponse(BaseModel):
    items: list[CatalogResponse]
    limit: int
    offset: int


class CatalogClassListResponse(BaseModel):
    items: list[CatalogClassResponse]
    limit: int
    offset: int

