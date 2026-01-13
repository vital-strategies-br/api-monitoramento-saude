from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.relacao_service import RelacaoService

router = APIRouter(tags=["relacao"])
service = RelacaoService()


class Identificador(BaseModel):
    tipo: str = Field(..., examples=["cpf", "cns"])
    valor: str = Field(..., examples=["123.456.789-01"])

    @field_validator("valor")
    @classmethod
    def normalizar_valor(cls, v: str, info):
        tipo = info.data.get("tipo")
        if tipo in {"cpf", "cns"}:
            return "".join(ch for ch in v if ch.isdigit())
        return v.strip()


class RelacaoRequest(BaseModel):
    tipo_evento: str = Field(..., examples=["violencia"])
    identificadores: List[Identificador]

    @model_validator(mode="after")
    def validar_limite_identificadores(self):
        if not self.identificadores:
            raise ValueError("É necessário informar ao menos um identificador")
        if len(self.identificadores) > 10:
            raise ValueError("Máximo de 10 identificadores por requisição")
        return self


class RelacaoResponse(BaseModel):
    relacionado: bool


@router.post("/relacao", response_model=RelacaoResponse)
async def relacao(
    payload: RelacaoRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> RelacaoResponse:
    pares = [(i.tipo, i.valor) for i in payload.identificadores]

    relacionado = await service.consultar(
        db,
        endpoint=str(request.url.path),
        tipo_evento=payload.tipo_evento,
        pares_identificadores=pares,
    )

    return RelacaoResponse(relacionado=relacionado)
