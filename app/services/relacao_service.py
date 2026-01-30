import logging
import orjson
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.metricas_repo import MetricasRepository
from app.db.repositories.relacao_repo import RelacaoRepository
from app.models.individuo_evento import IndividuoEvento
from app.services.exceptions import IdentificadoresConflitantesError

logger = logging.getLogger("app.metricas")


class RelacaoService:
    def __init__(self) -> None:
        self._relacao_repo = RelacaoRepository()
        self._metricas_repo = MetricasRepository()

    async def buscar_evento_relacionado(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        tipo_evento: str,
        pares_identificadores: list[tuple[str, str]],
    ) -> IndividuoEvento | None:
        individuos = await self._relacao_repo.buscar_individuos(
            db,
            pares_identificadores=pares_identificadores,
        )

        if not individuos:
            evento = None
        elif len(individuos) > 1:
            logger.warning(
                orjson.dumps(
                    {
                        "event": "identificadores_conflitantes",
                        "tipo_evento": tipo_evento,
                        "individuos": individuos,
                        "pares": pares_identificadores,
                    }
                ).decode()
            )
            evento = None
            await self._registrar_metricas(
                db,
                endpoint=endpoint,
                tipo_evento=tipo_evento,
                positivo=False,
            )
            raise IdentificadoresConflitantesError(individuos)
        else:
            evento = await self._relacao_repo.buscar_evento_identificacao(
                db,
                tipo_evento=tipo_evento,
                individuo_id=individuos[0],
            )

        await self._registrar_metricas(
            db,
            endpoint=endpoint,
            tipo_evento=tipo_evento,
            positivo=(evento is not None),
        )

        return evento

    async def _registrar_metricas(
        self,
        db: AsyncSession,
        *,
        endpoint: str,
        tipo_evento: str,
        positivo: bool,
    ) -> None:
        try:
            await self._metricas_repo.incr_diario(
                db,
                endpoint=endpoint,
                tipo_evento=tipo_evento,
                dia=date.today(),
                positivo=positivo,
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
