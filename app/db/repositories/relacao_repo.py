from sqlalchemy import case, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.individuo_evento import IndividuoEvento
from app.models.individuo_identificador import IndividuoIdentificador


class RelacaoRepository:
    async def existe_relacao(
        self,
        db: AsyncSession,
        *,
        tipo_evento: str,
        pares_identificadores: list[tuple[str, str]],
    ) -> str | None:
        if not pares_identificadores:
            return None

        prioridade = case(
            (IndividuoEvento.metodo_identificacao == "modelo_semantica_explicita", 0),
            else_=1,
        )

        q = (
            select(IndividuoEvento.metodo_identificacao)
            .select_from(IndividuoIdentificador)
            .join(
                IndividuoEvento,
                IndividuoEvento.individuo_id == IndividuoIdentificador.individuo_id,
            )
            .where(IndividuoEvento.tipo_evento == tipo_evento)
            .where(IndividuoEvento.metodo_identificacao != "n_a")
            .where(
                tuple_(
                    IndividuoIdentificador.tipo_identificador,
                    IndividuoIdentificador.valor_identificador,
                ).in_(pares_identificadores)
            )
            .order_by(prioridade)
            .limit(1)
        )

        res = await db.execute(q)
        row = res.first()

        return row[0] if row else None
