from typing import Any
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"issues": [{"location": list(item["loc"]), "message": item["msg"]} for item in exc.errors()]}
        return JSONResponse(error_body("validation_error", "Request validation failed", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return JSONResponse(error_body("not_found", "Resource not found"), status_code=404)
        return JSONResponse(error_body("http_error", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    def internal_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("annotate_tool").exception("Unhandled API error", exc_info=exc)
        return JSONResponse(
            error_body("internal_error", "Internal server error"), status_code=500
        )
