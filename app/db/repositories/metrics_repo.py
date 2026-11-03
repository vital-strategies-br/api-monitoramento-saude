from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MetricsRepository:
    async def increment_daily(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        event_type: str,
        identification_method: str | None,
        day: date,
        positive: bool,
    ) -> None:
        await db.execute(
            text(
                """
                INSERT INTO monitoramento.metricas_diarias_endpoint
                    (endpoint, tipo_evento, metodo_identificacao, data, total_chamadas, respostas_positivas, updated_at)
                VALUES
                    (:endpoint, :tipo_evento, :metodo_identificacao, :data, 1, :pos, now())
                ON CONFLICT (endpoint, tipo_evento, metodo_identificacao, data)
                DO UPDATE SET
                    total_chamadas = monitoramento.metricas_diarias_endpoint.total_chamadas + 1,
                    respostas_positivas = monitoramento.metricas_diarias_endpoint.respostas_positivas + EXCLUDED.respostas_positivas,
                    updated_at = now()
                """
            ),
            {
                "endpoint": endpoint,
                "tipo_evento": event_type,
                "metodo_identificacao": identification_method or "n_a",
                "data": day,
                "pos": 1 if positive else 0,
            },
        )
