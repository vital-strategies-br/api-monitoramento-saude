import logging
from collections.abc import Callable, Coroutine
from http import HTTPStatus
from typing import Any

import orjson
from fastapi import Request
from fastapi.exceptions import RequestValidationError
# FastAPI raises Starlette's HTTPException (the base class) for unparseable bodies.
from starlette.exceptions import HTTPException
from fastapi.routing import APIRoute
from starlette.responses import Response

from app.core import messages
from app.utils.http import error_response
from app.utils.validation import format_error

logger = logging.getLogger("app.errors")


class PlainErrorRoute(APIRoute):
    """Route whose request errors are a 422 with `detail` as one Portuguese string.

    Also turns FastAPI's own 400 for a body it cannot parse (invalid UTF-8,
    nesting deeper than the JSON parser allows) into the same "JSON malformado"
    422. The route's own code never raises 400.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def plain_error_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return error_response(HTTPStatus.UNPROCESSABLE_ENTITY, format_error(exc.errors()[0]))
            except HTTPException as exc:
                if exc.status_code != HTTPStatus.BAD_REQUEST:
                    raise
                return error_response(HTTPStatus.UNPROCESSABLE_ENTITY, messages.VALIDATION_ERRORS["json_invalid"])

        return plain_error_handler


async def internal_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception(
        orjson.dumps(
            {
                "event": "internal_error",
                "method": request.method,
                "path": request.url.path,
            }
        ).decode()
    )
    return error_response(HTTPStatus.INTERNAL_SERVER_ERROR, messages.INTERNAL_ERROR)
