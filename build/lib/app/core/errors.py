import logging

import orjson
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

logger = logging.getLogger("app.errors")


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
