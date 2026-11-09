from collections.abc import Collection
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry_event import TelemetryEvent


class TelemetryEventRepository:
    async def insert_new(
        self,
        db: AsyncSession,
        *,
        events: list[dict[str, Any]],
        created_by: str,
    ) -> set[UUID]:
        """Insert events in one statement, skipping any that violate a unique rule.

        Returns the evento_ids actually inserted. Skipped rows are either an
        already stored evento_id or a second alerta_encerrado for the same alert.
        """
        if not events:
            return set()
        statement = (
            insert(TelemetryEvent)
            .values([{**event, "internal_id": uuid4(), "created_by": created_by} for event in events])
            .on_conflict_do_nothing()
            .returning(TelemetryEvent.evento_id)
        )
        result = await db.execute(statement)
        return set(result.scalars().all())

    async def find_payloads(
        self,
        db: AsyncSession,
        *,
        evento_ids: Collection[UUID],
    ) -> dict[UUID, dict[str, Any]]:
        if not evento_ids:
            return {}
        result = await db.execute(
            select(TelemetryEvent.evento_id, TelemetryEvent.payload)
            .where(TelemetryEvent.evento_id.in_(evento_ids))
        )
        return {row.evento_id: row.payload for row in result}
