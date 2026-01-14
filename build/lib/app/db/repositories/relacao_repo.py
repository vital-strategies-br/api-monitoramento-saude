from sqlalchemy import select, tuple_
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
    ) -> bool:
        if not pares_identificadores:
            return False

        q = (
            select(1)
            .select_from(IndividuoIdentificador)
            .join(
                IndividuoEvento,
                IndividuoEvento.individuo_id == IndividuoIdentificador.individuo_id,
            )
            .where(IndividuoEvento.tipo_evento == tipo_evento)
            .where(
                tuple_(
                    IndividuoIdentificador.tipo_identificador,
                    IndividuoIdentificador.valor_identificador,
                ).in_(pares_identificadores)
            )
            .limit(1)
        )
        res = await db.execute(q)
        return res.first() is not None
