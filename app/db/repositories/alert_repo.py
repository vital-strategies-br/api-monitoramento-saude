from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertResponse, AlertResponseIdentifier
from app.models.individual_event import IndividualEvent


class AlertRepository:
    async def record_response(
        self,
        db: AsyncSession,
        *,
        event: IndividualEvent,
        endpoint: str,
        identifier_pairs: list[tuple[str, str]],
    ) -> UUID:
        # An upsert returns the existing ID even when concurrent requests are
        # the first to serve this event. Each request still gets its own response.
        statement = insert(Alert).values(
            id=uuid4(), individuo_evento_id=event.id,
        )
        result = await db.execute(
            statement.on_conflict_do_update(
                index_elements=[Alert.individuo_evento_id],
                set_={"individuo_evento_id": statement.excluded.individuo_evento_id},
            ).returning(Alert.id)
        )
        alert_id = result.scalar_one()
        response_id = uuid4()
        await db.execute(insert(AlertResponse).values(
            id=response_id,
            alerta_id=alert_id,
            endpoint=endpoint,
            tipo_evento=event.tipo_evento,
            metodo_identificacao=event.metodo_identificacao,
            data_identificacao=event.data_identificacao,
            banco_origem_identificacao=event.banco_origem_identificacao,
            id_registro_identificacao=event.id_registro_identificacao,
        ))
        await db.execute(insert(AlertResponseIdentifier), [
            {"resposta_id": response_id, "tipo_identificador": kind,
             "valor_identificador": value}
            for kind, value in sorted(set(identifier_pairs))
        ])
        return alert_id
