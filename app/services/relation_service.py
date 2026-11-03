import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.alert_repo import AlertRepository
from app.db.repositories.metrics_repo import MetricsRepository
from app.db.repositories.relation_repo import RelationRepository
from app.models.individual_event import IndividualEvent
from app.services.exceptions import ConflictingIdentifiersError

logger = logging.getLogger("app.metricas")


@dataclass(frozen=True)
class RelatedAlert:
    event: IndividualEvent
    alert_id: UUID


class RelationService:
    def __init__(self) -> None:
        self._relation_repo = RelationRepository()
        self._metrics_repo = MetricsRepository()
        self._alert_repo = AlertRepository()

    async def find_related_event(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        event_type: str,
        identifier_pairs: list[tuple[str, str]],
    ) -> RelatedAlert | None:
        individuals = await self._relation_repo.find_individuals(
            db,
            identifier_pairs=identifier_pairs,
        )

        if len(individuals) > 1:
            logger.warning(
                orjson.dumps(
                    {
                        "event": "identificadores_conflitantes",
                        "tipo_evento": event_type,
                        "individuos": individuals,
                        "pares": identifier_pairs,
                    }
                ).decode()
            )
            await self._record_negative_metric(db, endpoint=endpoint, event_type=event_type)
            raise ConflictingIdentifiersError(individuals)

        event = (
            await self._relation_repo.find_identification_event(
                db,
                event_type=event_type,
                individual_id=individuals[0],
            )
            if individuals
            else None
        )

        if event is None:
            await self._record_negative_metric(db, endpoint=endpoint, event_type=event_type)
            return None

        # Audit and daily totals must either both persist or both roll back.
        # Never return a positive response after losing its audit record.
        try:
            alert_id = await self._alert_repo.record_response(
                db, event=event, endpoint=endpoint,
                identifier_pairs=identifier_pairs,
            )
            await self._metrics_repo.increment_daily(
                db, endpoint=endpoint, event_type=event_type,
                identification_method=event.metodo_identificacao,
                day=date.today(), positive=True,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return RelatedAlert(event=event, alert_id=alert_id)

    async def _record_negative_metric(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        event_type: str,
    ) -> None:
        # Best effort: a metrics failure must not fail a negative response.
        try:
            await self._metrics_repo.increment_daily(
                db,
                endpoint=endpoint,
                event_type=event_type,
                identification_method=None,
                day=date.today(),
                positive=False,
            )
            await db.commit()
        except Exception:
            logger.exception(
                orjson.dumps(
                    {
                        "event": "metric_write_failed",
                        "endpoint": endpoint,
                        "tipo_evento": event_type,
                    }
                ).decode()
            )
            await db.rollback()
