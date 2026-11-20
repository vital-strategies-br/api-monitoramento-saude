from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.responses import MAX_BATCH_SIZE, MAX_BODY_BYTES, TELEMETRY_RESPONSES
from app.core.errors import PlainErrorRoute
from app.db.session import get_db
from app.schemas.telemetry import TelemetryBatchRequest, TelemetryBatchResponse
from app.services.exceptions import BatchTooLargeError, EmptyBatchError
from app.services.telemetry_service import TelemetryService
from app.utils.http import api_key_fingerprint

router = APIRouter(tags=["telemetria"], route_class=PlainErrorRoute)
service = TelemetryService()


@router.post(
    "/telemetria/eventos",
    response_model=TelemetryBatchResponse,
    summary="Receber lote de eventos",
    description=(
        f"Recebe de 1 a {MAX_BATCH_SIZE} eventos (e no máximo {MAX_BODY_BYTES} bytes) do plugin "
        "de alertas, enviados pelo backend da Pitang: exibição do alerta, navegação na orientação, "
        "botões de ação e o feedback registrado pelos profissionais. Usa a mesma autenticação da "
        "API de consulta (`X-API-Key`, `X-Timestamp`, `X-Signature`).\n\n"
        "**Erros**\n"
        "- Todo erro da chamada tem o corpo `{\"detail\": \"<texto>\"}`: um único texto, nunca "
        "lista ou objeto. Os textos possíveis estão nos exemplos de cada status abaixo.\n"
        "- Problemas em eventos individuais não são erro da chamada: o status é 200 e cada evento "
        "inválido volta em `rejeitados` como `{evento_id, campo, mensagem}`.\n\n"
        "**Regras por evento**\n"
        "- Cada evento cai em exatamente um grupo: `aceitos + duplicados + len(rejeitados)` "
        "é igual ao total enviado.\n"
        "- `evento_id` repetido não é erro: é ignorado (vale o primeiro) e contado em `duplicados`.\n"
        "- Um segundo `alerta_encerrado` para o mesmo `alerta_id` volta em `rejeitados`.\n"
        "- `alerta_id` desconhecido não é motivo de rejeição.\n"
        "- Validação: objeto JSON; `evento_id` e `alerta_id` UUID e não nulos; `evento` do "
        "contrato v1; sem `alerta_tipo`, `alerta_origem`, `atualizacao_base_id` e `paciente_id`; "
        "sem `\\u0000`, Unicode inválido, `NaN` ou `Infinity` em nenhum valor. Os demais campos "
        "são armazenados como recebidos; `null` neles é aceito."
    ),
    responses=TELEMETRY_RESPONSES,
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
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(e))
    except BatchTooLargeError as e:
        raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail=str(e))
