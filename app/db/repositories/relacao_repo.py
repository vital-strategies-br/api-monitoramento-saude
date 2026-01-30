from sqlalchemy import case, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.individuo_evento import IndividuoEvento
from app.models.individuo_identificador import IndividuoIdentificador


class RelacaoRepository:
    async def buscar_individuos(
        self,
        db: AsyncSession,
        *,
        pares_identificadores: list[tuple[str, str]],
    ) -> list[int]:
        if not pares_identificadores:
            return []

        q = (
            select(IndividuoIdentificador.individuo_id)
            .where(
                tuple_(
                    IndividuoIdentificador.tipo_identificador,
                    IndividuoIdentificador.valor_identificador,
                ).in_(pares_identificadores)
            )
            .distinct()
        )

        res = await db.execute(q)
        return list(res.scalars().all())

    async def buscar_evento_identificacao(
        self,
        db: AsyncSession,
        *,
        individuo_id: int,
        tipo_evento: str,
    ) -> IndividuoEvento | None:
        prioridade = case(
            (IndividuoEvento.metodo_identificacao == "modelo_semantica_explicita", 0),
            else_=1,
        )

        q = (
            select(IndividuoEvento)
            .where(IndividuoEvento.individuo_id == individuo_id)
            .where(IndividuoEvento.tipo_evento == tipo_evento)
            .where(IndividuoEvento.metodo_identificacao != "n_a")
            .order_by(prioridade.asc(), IndividuoEvento.data_identificacao.desc())
            .limit(1)
        )

        res = await db.execute(q)
        return res.scalar_one_or_none()
