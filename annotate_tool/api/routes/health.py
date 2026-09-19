from fastapi import APIRouter, Depends

from annotate_tool.api.dependencies import AppContext, get_context


router = APIRouter()


@router.get("/health")
def health(context: AppContext = Depends(get_context)) -> dict[str, str]:
    context.database.check_accessible()
    context.paths.validate_writable()
    return {"status": "ok", "database": "available", "storage": "writable"}

