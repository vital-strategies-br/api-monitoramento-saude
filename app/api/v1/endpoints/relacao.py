from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.relacao_service import RelacaoService
from app.services.exceptions import IdentificadoresConflitantesError

router = APIRouter(tags=["relacao"])
service = RelacaoService()

TipoEvento = Literal["violencia"]
TipoMetodoIdentificacao = Literal[
    "notificacao_sinan",
    "modelo_semantica_explicita",
    "modelo_classificacao_provavel",
]


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
    metodo_identificacao: TipoMetodoIdentificacao | None = Field(
        None,
        description="Método que foi usado para verificar a relação.",
        examples=["modelo_semantica_explicita", "modelo_classificacao_provavel", "notificacao_sinan"],
    )
    data_identificacao: str | None = Field(
        None,
        description="Data em que o evento foi identificado para o indivíduo relacionado, no formato AAAA-MM-DD.",
        examples=["2023-08-15"],
    )
    banco_origem_identificacao: str | None = Field(
        None,
        description="Banco de origem do registro de identificação do indivíduo.",
        examples=["e-SUS APS"],
    )
    id_registro_identificacao: str | None = Field(
        None,
        description="Identificador do registro de identificação do indivíduo no banco de origem (para e-SUS APS = co_seq_atendimento).",
        examples=["1234567890"],
    )


class RelacaoErroConflito(BaseModel):
    detail: str = Field(
        ...,
        examples=["Identificadores informados correspondem a mais de um indivíduo."],
    )
    code: Literal["IDENTIFICADORES_CONFLITANTES"] = Field(
        ..., examples=["IDENTIFICADORES_CONFLITANTES"]
    )


@router.post(
    "/relacao/{tipo_evento}",
    response_model=RelacaoResponse,
    # response_model_exclude_none=True,
    summary="Verificar relação",
    description=(
        "Verifica se existe relação entre **qualquer** dos identificadores informados e o `tipo_evento`. "
        "Os identificadores devem pertencer a um mesmo indivíduo para que a relação com um evento seja confirmada ou não. "
        "A resposta é `relacionado=true` quando há pelo menos um registro de evento para o mesmo indivíduo associado."
        "O campo `metodo_identificacao` indica o método utilizado para estabelecer a relação."
    ),
    responses={
        401: {"description": "Não autorizado (API Key/HMAC ausentes ou inválidos)."},
        409: {"description": "Identificadores correspondem a mais de um indivíduo."},
        422: {"description": "Erro de validação do payload."},
        500: {"description": "Erro interno."},
    },
)
async def relacao(
    tipo_evento: TipoEvento = Path(
        ...,
        description="Tipo do evento que será consultado.",
        examples=["violencia"],
    ),
    payload: RelacaoRequest = ...,
    request: Request = ...,
    db: AsyncSession = Depends(get_db),
) -> RelacaoResponse:
    pares = [(i.tipo, i.valor) for i in payload.identificadores]

    try:
        evento = await service.buscar_evento_relacionado(
            db,
            endpoint=str(request.url.path),
            tipo_evento=tipo_evento,
            pares_identificadores=pares,
        )
    except IdentificadoresConflitantesError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "IDENTIFICADORES_CONFLITANTES", "message": str(e)},
        )

    if evento is None:
        return RelacaoResponse(relacionado=False)

    return RelacaoResponse(
        relacionado=True,
        metodo_identificacao=evento.metodo_identificacao,
        data_identificacao=str(evento.data_identificacao),
        banco_origem_identificacao=(
            str(evento.banco_origem_identificacao)
            if evento.banco_origem_identificacao is not None
            else None
        ),
        id_registro_identificacao=evento.id_registro_identificacao,
    )
