"""OpenAPI documentation of every response, built from the same message constants
the API returns at runtime (app.core.messages), so Swagger and behaviour match.
"""

from http import HTTPStatus
from typing import Any

from app.core import messages
from app.core.config import settings
from app.schemas.common import ErrorDetail
from app.utils.openapi import json_examples

# OpenAPI docs are generated once, so they show the limits configured at startup.
MAX_BATCH_SIZE = settings.TELEMETRY_MAX_BATCH_SIZE
MAX_BODY_BYTES = settings.MAX_REQUEST_BODY_BYTES

ResponseDocs = dict[int | str, dict[str, Any]]

_EXAMPLE_UUID = "7a1e5c30-9b2d-4f8a-8c64-3d0e1f2a4b55"


def error_doc(description: str, *, headers: dict[str, Any] | None = None, **examples: str) -> dict[str, Any]:
    """Response doc for an `ErrorDetail` body, one named example per `detail` text."""
    doc: dict[str, Any] = {
        "model": ErrorDetail,
        "description": description,
        "content": json_examples(**{
            name: (detail, {"detail": detail}) for name, detail in examples.items()
        }),
    }
    if headers:
        doc["headers"] = headers
    return doc


def _rejection(campo: str, mensagem: str, evento_id: str | None = _EXAMPLE_UUID) -> dict[str, Any]:
    return {"evento_id": evento_id, "campo": campo, "mensagem": mensagem}


# --- Every authenticated route (enforced by middleware) -----------------------

COMMON_RESPONSES: ResponseDocs = {
    HTTPStatus.UNAUTHORIZED: error_doc(
        "Não autorizado: `X-API-Key` ausente ou inválida, ou, com HMAC ativo, "
        "`X-Timestamp`/`X-Signature` ausentes, fora da tolerância ou inválidos. "
        "Mesma resposta da API de consulta (spec 10).",
        api_key=messages.UNAUTHORIZED,
        timestamp_invalido=messages.TIMESTAMP_INVALID,
        timestamp_expirado=messages.TIMESTAMP_STALE,
        assinatura_ausente=messages.SIGNATURE_MISSING,
        assinatura_invalida=messages.SIGNATURE_INVALID,
    ),
    HTTPStatus.FORBIDDEN: error_doc(
        "Origem (`Origin`) não permitida, quando a verificação de origem está ativa.",
        origem=messages.ORIGIN_NOT_ALLOWED,
    ),
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: error_doc(
        f"Corpo da requisição acima de {MAX_BODY_BYTES} bytes. Verificado antes da autenticação.",
        bytes=messages.BODY_TOO_LARGE.format(max_bytes=MAX_BODY_BYTES),
    ),
    HTTPStatus.TOO_MANY_REQUESTS: error_doc(
        f"Limite de {settings.RATE_LIMIT_REQUESTS} requisições a cada "
        f"{settings.RATE_LIMIT_WINDOW_SECONDS} segundos por IP excedido (quando ativo). "
        "Aguardar os segundos de `Retry-After` e reenviar.",
        headers={"Retry-After": {
            "description": "Segundos até a próxima janela do limite.",
            "schema": {"type": "integer", "minimum": 1},
        }},
        limite=messages.RATE_LIMITED.format(segundos=settings.RATE_LIMIT_WINDOW_SECONDS),
    ),
    HTTPStatus.INTERNAL_SERVER_ERROR: error_doc("Erro interno.", erro_interno=messages.INTERNAL_ERROR),
}


# --- POST /api/v1/telemetria/eventos ------------------------------------------

_V = messages.VALIDATION_ERRORS

TELEMETRY_RESPONSES: ResponseDocs = {
    HTTPStatus.OK: {
        "description": (
            "Lote recebido. `aceitos + duplicados + len(rejeitados)` é igual ao total enviado. "
            "Reenviar somente os eventos de `rejeitados`, corrigidos."
        ),
        "content": json_examples(
            lote_aceito=("Lote aceito", {"aceitos": 1, "duplicados": 0, "rejeitados": []}),
            lote_com_duplicado=("Lote com evento já recebido", {"aceitos": 1, "duplicados": 1, "rejeitados": []}),
            rejeicoes=(
                "Um exemplo de cada tipo de rejeição",
                {
                    "aceitos": 1,
                    "duplicados": 0,
                    "rejeitados": [
                        _rejection("evento_id", _V["missing"], evento_id=None),
                        _rejection("alerta_id", messages.NULL_VALUE),
                        _rejection("alerta_id", _V["uuid_parsing"]),
                        _rejection("evento", _V["literal_error"]),
                        _rejection("eventos[4]", _V["model_type"], evento_id=None),
                        _rejection("eventos[5]", messages.NULL_VALUE, evento_id=None),
                        _rejection("paciente_id", messages.FORBIDDEN_FIELD),
                        _rejection("extra.lista.1", messages.INVALID_TEXT),
                        _rejection("etapa", messages.INVALID_NUMBER),
                        _rejection("alerta_id", messages.CLOSURE_ALREADY_RECORDED),
                    ],
                },
            ),
        ),
    },
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: error_doc(
        "Lote acima do limite de eventos ou de bytes. Dividir em lotes menores e reenviar "
        "com os mesmos `evento_id`.",
        eventos=messages.BATCH_TOO_LARGE.format(max_eventos=MAX_BATCH_SIZE),
        bytes=messages.BODY_TOO_LARGE.format(max_bytes=MAX_BODY_BYTES),
    ),
    HTTPStatus.UNPROCESSABLE_ENTITY: error_doc(
        "Chamada inválida (o lote inteiro). Corrigir o cliente; não reenviar automaticamente. "
        "Problemas em eventos individuais não geram 422: voltam em `rejeitados` com status 200.",
        lote_vazio=messages.EMPTY_BATCH,
        corpo_ausente=messages.BODY_MISSING,
        json_malformado=_V["json_invalid"],
        corpo_nao_objeto=_V["model_attributes_type"],
        eventos_ausente=f"eventos: {_V['missing']}",
        eventos_nulo=f"eventos: {messages.NULL_VALUE}",
        eventos_nao_lista=f"eventos: {_V['list_type']}",
    ),
    HTTPStatus.INTERNAL_SERVER_ERROR: error_doc(
        "Erro interno: nada do lote foi armazenado. Reenviar o mesmo lote, com os mesmos "
        "`evento_id`, com espera crescente.",
        erro_interno=messages.INTERNAL_ERROR,
    ),
}
