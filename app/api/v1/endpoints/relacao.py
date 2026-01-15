from typing import List

from fastapi import APIRouter, Depends, Request, Path
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.relacao_service import RelacaoService

router = APIRouter(tags=["relacao"])
service = RelacaoService()


class Identificador(BaseModel):
    tipo: str = Field(
        ...,
        description="Tipo do identificador (ex.: cpf, cns).",
        examples=["cpf", "cns"],
    )
    valor: str = Field(
        ...,
        description="Valor do identificador. Para `cpf` e `cns`, o valor é normalizado removendo caracteres não numéricos.",
        examples=["123.456.789-01"],
    )

    @field_validator("valor")
    @classmethod
    def normalizar_valor(cls, v: str, info):
        tipo = info.data.get("tipo")
        if tipo in {"cpf", "cns"}:
            return "".join(ch for ch in v if ch.isdigit())
        return v.strip()


class RelacaoRequest(BaseModel):
    identificadores: List[Identificador] = Field(
        ...,
        description="Lista de identificadores a serem consultados. Mínimo: 1. Máximo: 10.",
    )

    @model_validator(mode="after")
    def validar_limite_identificadores(self):
        if not self.identificadores:
            raise ValueError("É necessário informar ao menos um identificador")
        if len(self.identificadores) > 10:
            raise ValueError("Máximo de 10 identificadores por requisição")
        return self


class RelacaoResponse(BaseModel):
    relacionado: bool = Field(
        ...,
        description="Indica se existe ao menos um indivíduo com algum dos identificadores informado e com evento do tipo consultado.",
        examples=[True, False],
    )


@router.post(
    "/relacao/{tipo_evento}",
    response_model=RelacaoResponse,
    summary="Verificar relação",
    description=(
        "Verifica se existe relação entre **qualquer** dos identificadores informados e o `tipo_evento`. "
        "A resposta é `relacionado=true` quando há pelo menos um registro de evento para o mesmo indivíduo associado."
    ),
    responses={
        401: {"description": "Não autorizado (API Key/HMAC ausentes ou inválidos)."},
        422: {"description": "Erro de validação do payload."},
        500: {"description": "Erro interno."},
    },
)
async def relacao(
    tipo_evento: str = Path(
        ..., description="Tipo do evento que será consultado.", examples=["violencia"]
    ),
    payload: RelacaoRequest = ...,
    request: Request = ...,
    db: AsyncSession = Depends(get_db),
) -> RelacaoResponse:
    pares = [(i.tipo, i.valor) for i in payload.identificadores]

    relacionado = await service.consultar(
        db,
        endpoint=str(request.url.path),
        tipo_evento=tipo_evento,
        pares_identificadores=pares,
    )

    return RelacaoResponse(relacionado=relacionado)
