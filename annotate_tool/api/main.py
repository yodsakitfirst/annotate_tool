from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse

from annotate_tool.api.dependencies import Settings, build_context
from annotate_tool.api.errors import install_error_handlers
from annotate_tool.api.routes import annotations, catalogs, exports, health, images, media, projects


logger = logging.getLogger("annotate_tool")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    context = build_context(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting Annotation Desk")
        try:
            context.paths.validate_writable()
            context.database.initialize()
            context.database.check_accessible()
        except Exception:
            logger.exception("Application startup validation failed")
            raise
        app.state.context = context
        if "ANNOTATE_TOOL_DATA_DIR" not in os.environ:
            logger.warning(
                "ANNOTATE_TOOL_DATA_DIR is not set; uploaded data may be on ephemeral storage"
            )
        logger.info("Annotation Desk startup validation complete")
        yield

    app = FastAPI(title="Annotation Platform", lifespan=lifespan)
    app.state.context = context
    install_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(catalogs.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(images.router, prefix="/api/v1")
    app.include_router(annotations.router, prefix="/api/v1")
    app.include_router(exports.router, prefix="/api/v1")
    app.include_router(media.router)

    @app.get("/assets/{asset_path:path}")
    def frontend_asset(asset_path: str):
        from annotate_tool.api.errors import ApiError
        asset_root = resolved_settings.frontend_dist.resolve() / "assets"
        try:
            target = (asset_root / asset_path).resolve(strict=True)
            target.relative_to(asset_root)
        except (OSError, ValueError) as exc:
            raise ApiError(404, "not_found", "Resource not found") from exc
        return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/{spa_path:path}")
    def frontend_fallback(spa_path: str):
        from annotate_tool.api.errors import ApiError
        if spa_path.startswith(("api/", "media/")):
            raise ApiError(404, "not_found", "Resource not found")
        index = resolved_settings.frontend_dist.resolve() / "index.html"
        if not index.is_file():
            raise ApiError(503, "frontend_unavailable", "Frontend build is unavailable")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return app


app = create_app()
