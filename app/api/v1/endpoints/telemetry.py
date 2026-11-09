from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import messages
from app.core.config import settings
from app.core.errors import PlainErrorRoute
from app.db.session import get_db
from app.schemas.common import ErrorDetail
from app.schemas.telemetry import (
    RESPONSE_200_CONTENT,
    TelemetryBatchRequest,
    TelemetryBatchResponse,
)
from app.utils.openapi import json_examples
from app.services.exceptions import BatchTooLargeError, EmptyBatchError
from app.services.telemetry_service import TelemetryService
from app.utils.http import api_key_fingerprint

router = APIRouter(tags=["telemetria"], route_class=PlainErrorRoute)
service = TelemetryService()

# OpenAPI docs are generated once, so they show the limits configured at startup.
MAX_BATCH_SIZE = settings.TELEMETRY_MAX_BATCH_SIZE
MAX_BODY_BYTES = settings.MAX_REQUEST_BODY_BYTES


@router.post(
    "/telemetria/eventos",
    response_model=TelemetryBatchResponse,
    summary="Receber lote de eventos",
    description=(
        f"Recebe de 1 a {MAX_BATCH_SIZE} eventos (e no máximo {MAX_BODY_BYTES} bytes) do plugin "
        "de alertas para o painel de monitoramento, enviados pelo backend da Pitang. Usa a mesma "
        "autenticação da API de consulta (`X-API-Key`, `X-Timestamp`, `X-Signature`).\n\n"
        "- Cada evento cai em exatamente um grupo: `aceitos + duplicados + len(rejeitados)` "
        "é igual ao total enviado.\n"
        "- Evento inválido não invalida o lote: volta em `rejeitados`, um item por evento.\n"
        "- `evento_id` repetido não é erro: é ignorado (vale o primeiro) e contado em `duplicados`.\n"
        "- Um segundo `alerta_encerrado` para o mesmo `alerta_id` volta em `rejeitados`.\n"
        "- `alerta_id` desconhecido não é motivo de rejeição.\n"
        "- Validação por evento: objeto JSON, `evento_id` e `alerta_id` UUID, `evento` do "
        "contrato v1 e ausência de `alerta_tipo`, `alerta_origem`, `atualizacao_base_id` e "
        "`paciente_id`. Os demais campos são armazenados como recebidos."
    ),
    responses={
        200: {
            "description": "Lote recebido. Pode conter eventos rejeitados; reenviar somente esses, corrigidos.",
            "content": RESPONSE_200_CONTENT,
        },
        413: {
            "model": ErrorDetail,
            "description": "Lote acima do limite de eventos ou de bytes. Dividir em lotes menores e reenviar.",
            "content": json_examples(
                eventos=("Acima do limite de eventos", {"detail": str(BatchTooLargeError(MAX_BATCH_SIZE))}),
                bytes=("Acima do limite de bytes", {"detail": messages.BODY_TOO_LARGE.format(max_bytes=MAX_BODY_BYTES)}),
            ),
        },
        422: {
            "model": ErrorDetail,
            "description": (
                "Chamada inválida: lote vazio, JSON malformado ou `eventos` ausente. "
                "Corrigir o cliente; não reenviar automaticamente."
            ),
            "content": json_examples(
                lote_vazio=("Lote vazio", {"detail": str(EmptyBatchError())}),
                json_malformado=("JSON malformado", {"detail": messages.VALIDATION_ERRORS["json_invalid"]}),
                eventos_ausente=(
                    "Campo eventos ausente",
                    {"detail": f"eventos: {messages.VALIDATION_ERRORS['missing']}"},
                ),
            ),
        },
        500: {"description": "Erro interno. Reenviar o mesmo lote, com os mesmos `evento_id`, com espera crescente."},
    },
)
async def receive_events(
    payload: TelemetryBatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TelemetryBatchResponse:
    # ApiAuthMiddleware has already validated this header.
    created_by = api_key_fingerprint(request.headers["x-api-key"])
    try:
        return await service.receive_batch(db, events=payload.eventos, created_by=created_by)
    except EmptyBatchError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except BatchTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
