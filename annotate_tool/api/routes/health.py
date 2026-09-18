from fastapi import APIRouter, Depends

from annotate_tool.api.dependencies import AppContext, get_context


router = APIRouter()


@router.get("/health")
def health(context: AppContext = Depends(get_context)) -> dict[str, str]:
    with context.database.connect() as connection:
        connection.execute("SELECT 1").fetchone()
    probe = context.paths.staging / ".write-probe"
    probe.write_bytes(b"")
    probe.unlink()
    return {"status": "ok", "database": "available", "storage": "writable"}

