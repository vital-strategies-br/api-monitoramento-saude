from sqlalchemy import case, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.individual_event import IndividualEvent
from app.models.individual_identifier import IndividualIdentifier


class RelationRepository:
    async def find_individuals(
        self,
        db: AsyncSession,
        *,
        identifier_pairs: list[tuple[str, str]],
    ) -> list[int]:
        if not identifier_pairs:
            return []

        q = (
            select(IndividualIdentifier.individuo_id)
            .where(
                tuple_(
                    IndividualIdentifier.tipo_identificador,
                    IndividualIdentifier.valor_identificador,
                ).in_(identifier_pairs)
            )
            .distinct()
        )

        res = await db.execute(q)
        return list(res.scalars().all())

    async def find_identification_event(
        self,
        db: AsyncSession,
        *,
        individual_id: int,
        event_type: str,
    ) -> IndividualEvent | None:
        priority = case(
            (IndividualEvent.metodo_identificacao == "notificacao_sinan", 0),
            (IndividualEvent.metodo_identificacao == "modelo_semantica_explicita", 1),
            else_=2,
        )

        q = (
            select(IndividualEvent)
            .where(IndividualEvent.individuo_id == individual_id)
            .where(IndividualEvent.tipo_evento == event_type)
            .where(IndividualEvent.metodo_identificacao != "n_a")
            .where(IndividualEvent.gera_alerta.is_(True))
            .order_by(priority.asc(), IndividualEvent.data_identificacao.desc())
            .limit(1)
        )

        res = await db.execute(q)
        return res.scalar_one_or_none()
