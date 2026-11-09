from typing import Any

from fastapi import APIRouter, Depends

from app.api.v1.endpoints.relation import router as relation_router
from app.api.v1.endpoints.telemetry import router as telemetry_router
from app.core import messages
from app.core.auth_deps import swagger_api_key, swagger_hmac_headers
from app.core.config import settings
from app.schemas.common import ErrorDetail
from app.utils.openapi import json_examples

# Enforced by middleware on every authenticated route; documented once here.
COMMON_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {
        "model": ErrorDetail,
        "description": f"Corpo da requisição acima de {settings.MAX_REQUEST_BODY_BYTES} bytes.",
        "content": json_examples(bytes=(
            "Acima do limite de bytes",
            {"detail": messages.BODY_TOO_LARGE.format(max_bytes=settings.MAX_REQUEST_BODY_BYTES)},
        )),
    },
    429: {
        "model": ErrorDetail,
        "description": (
            f"Limite de {settings.RATE_LIMIT_REQUESTS} requisições a cada "
            f"{settings.RATE_LIMIT_WINDOW_SECONDS} segundos por IP excedido (quando ativo). "
            "Aguardar o tempo do cabeçalho `Retry-After`."
        ),
        "content": json_examples(limite=(
            "Limite excedido",
            {"detail": messages.RATE_LIMITED.format(segundos=settings.RATE_LIMIT_WINDOW_SECONDS)},
        )),
    },
}

api_router = APIRouter(dependencies=[Depends(swagger_api_key), Depends(swagger_hmac_headers)])
for router in (relation_router, telemetry_router):
    api_router.include_router(router, responses=COMMON_RESPONSES)
