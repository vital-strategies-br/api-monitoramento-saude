from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MetricasRepository:
    async def incr_diario(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        tipo_evento: str,
        dia: date,
        positivo: bool,
    ) -> None:
        await db.execute(
            text(
                """
                INSERT INTO monitoramento.metricas_diarias_endpoint
                    (endpoint, tipo_evento, data, total_chamadas, respostas_positivas, updated_at)
                VALUES
                    (:endpoint, :tipo_evento, :data, 1, :pos, now())
                ON CONFLICT (endpoint, tipo_evento, data)
                DO UPDATE SET
                    total_chamadas = monitoramento.metricas_diarias_endpoint.total_chamadas + 1,
                    respostas_positivas = monitoramento.metricas_diarias_endpoint.respostas_positivas + EXCLUDED.respostas_positivas,
                    updated_at = now()
                """
            ),
            {
                "endpoint": endpoint,
                "tipo_evento": tipo_evento,
                "data": dia,
                "pos": 1 if positivo else 0,
            },
        )
