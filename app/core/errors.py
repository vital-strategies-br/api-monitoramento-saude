import logging
from collections.abc import Callable, Coroutine
from typing import Any

import orjson
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.responses import Response
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.utils.http import error_response
from app.utils.validation import format_error

logger = logging.getLogger("app.errors")


class PlainErrorRoute(APIRoute):
    """Route whose 422 validation errors carry `detail` as one string, not a list."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def plain_error_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return error_response(422, format_error(exc.errors()[0]))

        return plain_error_handler


async def internal_exception_handler(request: Request, exc: Exception):
    logger.exception(
        orjson.dumps(
            {
                "event": "internal_error",
                "method": request.method,
                "path": request.url.path,
            }
        ).decode()
    )
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Erro interno"},
    )
