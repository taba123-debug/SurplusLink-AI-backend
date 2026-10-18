import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    pass


def error_response(status: int, code: str, message: str, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DatabaseUnavailable)
    async def database_error(request: Request, exc: DatabaseUnavailable):
        logger.warning("event=request_failed status=503 code=DATABASE_UNAVAILABLE")
        return error_response(503, "DATABASE_UNAVAILABLE", "Database connection is currently unavailable.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        logger.warning("event=request_failed status=%s", exc.status_code)
        return error_response(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail), exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        logger.warning("event=request_failed status=422 code=VALIDATION_ERROR")
        # Avoid echoing submitted input, which may contain secrets.
        return JSONResponse(status_code=422, content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": [{"location": list(error["loc"]), "type": error["type"]}
                        for error in exc.errors()],
        }})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("event=unhandled_error status=500", exc_info=app.state.settings.debug)
        return error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
