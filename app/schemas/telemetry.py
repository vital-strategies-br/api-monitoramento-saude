from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core import messages
from app.core.config import settings
from app.utils.openapi import json_examples

# Event names of contract version 1 (spec 8.3).
EventName = Literal[
    "alerta_exibido",
    "alerta_aberto",
    "orientacao_etapa_visualizada",
    "orientacao_fechada",
    "botao_acao_clicado",
    "feedback_iniciado",
    "feedback_fechado_sem_envio",
    "feedback_enviado",
    "alerta_encerrado",
]

# Fields an event must never carry (spec CE-11).
FORBIDDEN_FIELDS = frozenset({"alerta_tipo", "alerta_origem", "atualizacao_base_id", "paciente_id"})

EXAMPLE_EVENT: dict[str, Any] = {
    "evento_id": "5d0c9a52-1f7e-4b8a-a3c6-2e4f8b9d0a11",
    "evento": "alerta_exibido",
    "ocorrido_em": "2026-10-30T10:15:00-03:00",
    "plugin_versao": "1.0.0",
    "formulario_versao": "1.0.0",
    "alerta_id": "3f6c2a1e-8b4d-4c2f-9a7e-1d2b3c4d5e6f",
    "exibicao_id": "c41e7b90-6d2a-4e35-9f18-7a0b3c5d6e22",
    "atendimento_id": "ATD-000123",
    "profissional_id": "b7e2f04c9a1d...",
    "profissional_categoria": "enfermagem",
    "unidade_cnes": "0000000",
    "exibicao_numero_alerta": 1,
    "exibicao_numero_profissional": 1,
}


class TelemetryBatchRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"eventos": [EXAMPLE_EVENT]}]},
    )

    # Items are untyped here so a bad event never fails the whole batch:
    # each one is validated separately with TelemetryEventIn and, if invalid,
    # returned in `rejeitados`.
    eventos: list[Any] = Field(
        ...,
        description=(
            f"Lote de 1 a {settings.TELEMETRY_MAX_BATCH_SIZE} eventos. "
            "Cada evento é um objeto com o payload comum "
            "(`evento_id`, `evento`, `ocorrido_em`, `plugin_versao`, `formulario_versao`, "
            "`alerta_id`, `exibicao_id`, `atendimento_id`, `profissional_id`, "
            "`profissional_categoria`, `unidade_cnes`) mais os campos próprios do evento."
        ),
    )


class TelemetryEventIn(BaseModel):
    """Minimal per-event checks: what storage, dedup and closure uniqueness rely on.

    Other contract fields are kept as received in the stored payload.
    """

    model_config = ConfigDict(extra="allow")

    evento_id: UUID
    evento: EventName
    alerta_id: UUID

    @model_validator(mode="before")
    @classmethod
    def reject_forbidden_fields(cls, data: Any) -> Any:
        forbidden = sorted(FORBIDDEN_FIELDS & data.keys()) if isinstance(data, dict) else []
        if forbidden:
            raise PydanticCustomError("campo_proibido", messages.FORBIDDEN_FIELD, {"campo": forbidden[0]})
        return data


class RejectedEvent(BaseModel):
    evento_id: str | None = Field(
        ...,
        description="`evento_id` do evento rejeitado; nulo quando o evento não o informa.",
        examples=["7a1e5c30-9b2d-4f8a-8c64-3d0e1f2a4b55"],
    )
    campo: str = Field(..., description="Campo inválido.", examples=["alerta_id"])
    mensagem: str = Field(
        ..., description="Motivo da rejeição.", examples=["valor não é um UUID válido"],
    )


class TelemetryBatchResponse(BaseModel):
    aceitos: int = Field(..., ge=0, description="Quantidade de eventos aceitos.", examples=[1])
    duplicados: int = Field(
        ..., ge=0,
        description="Quantidade de eventos ignorados por `evento_id` já recebido (vale o primeiro).",
        examples=[0],
    )
    rejeitados: list[RejectedEvent] = Field(
        ...,
        description=(
            "Eventos inválidos, não aceitos, um item por evento. Reenviar somente estes, corrigidos."
        ),
    )


RESPONSE_200_CONTENT = json_examples(
    lote_aceito=(
        "Lote aceito",
        {"aceitos": 1, "duplicados": 0, "rejeitados": []},
    ),
    lote_com_rejeicao=(
        "Lote com duplicado e rejeitado",
        {
            "aceitos": 2,
            "duplicados": 1,
            "rejeitados": [{
                "evento_id": "7a1e5c30-9b2d-4f8a-8c64-3d0e1f2a4b55",
                "campo": "alerta_id",
                "mensagem": messages.VALIDATION_ERRORS["uuid_parsing"],
            }],
        },
    ),
)
