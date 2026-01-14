import logging
import orjson
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.metricas_repo import MetricasRepository
from app.db.repositories.relacao_repo import RelacaoRepository

logger = logging.getLogger("app.metricas")


class RelacaoService:
    def __init__(self) -> None:
        self._relacao_repo = RelacaoRepository()
        self._metricas_repo = MetricasRepository()

    async def consultar(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        tipo_evento: str,
        pares_identificadores: list[tuple[str, str]],
    ) -> bool:
        eh_positivo = await self._relacao_repo.existe_relacao(
            db,
            tipo_evento=tipo_evento,
            pares_identificadores=pares_identificadores,
        )

        # best-effort
        try:
            await self._metricas_repo.incr_diario(
                db,
                endpoint=endpoint,
                tipo_evento=tipo_evento,
                dia=date.today(),
                positivo=eh_positivo,
            )
            await db.commit()
        except Exception:
            logger.exception(
                orjson.dumps(
                    {
                        "event": "metric_write_failed",
                        "endpoint": endpoint,
                        "tipo_evento": tipo_evento,
                    }
                ).decode()
            )
            await db.rollback()

        return eh_positivo
