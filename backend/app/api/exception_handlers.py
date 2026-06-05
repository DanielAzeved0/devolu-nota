from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    sanitized_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        sanitized_error = {
            key: value
            for key, value in error.items()
            if key not in {"input", "ctx", "url"}
        }
        sanitized_errors.append(sanitized_error)

    return JSONResponse(
        status_code=422,
        content={"detail": sanitized_errors},
    )
