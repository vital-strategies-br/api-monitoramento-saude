import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import orjson
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import messages
from app.core.config import settings
from app.db.repositories.telemetry_repo import TelemetryEventRepository
from app.models.telemetry_event import ALERT_CLOSED_EVENT
from app.schemas.telemetry import RejectedEvent, TelemetryBatchResponse, TelemetryEventIn
from app.services.exceptions import BatchTooLargeError, EmptyBatchError
from app.utils.validation import error_field, error_message

logger = logging.getLogger("app.telemetria")

_EVENTO_ID = "evento_id"
_ALERTA_ID = "alerta_id"


@dataclass(frozen=True)
class _Candidate:
    event: TelemetryEventIn
    payload: dict[str, Any]


@dataclass
class _BatchOutcome:
    accepted: int = 0
    duplicates: int = 0
    rejected: list[RejectedEvent] = field(default_factory=list)

    def reject(self, raw: Any, campo: str, mensagem: str) -> None:
        self.rejected.append(RejectedEvent(evento_id=_raw_evento_id(raw), campo=campo, mensagem=mensagem))

    def to_response(self) -> TelemetryBatchResponse:
        return TelemetryBatchResponse(
            aceitos=self.accepted, duplicados=self.duplicates, rejeitados=self.rejected,
        )


class TelemetryService:
    """Receives dashboard event batches from the plugin backend (spec section 8).

    Every event ends in exactly one bucket, so
    aceitos + duplicados + len(rejeitados) == number of events sent.
    """

    def __init__(self) -> None:
        self._repo = TelemetryEventRepository()

    async def receive_batch(
        self,
        db: AsyncSession,
        *,
        events: Sequence[Any],
        created_by: str,
    ) -> TelemetryBatchResponse:
        self._validate_batch_size(len(events))
        outcome = _BatchOutcome()
        candidates = self._select_candidates(events, outcome)

        if candidates:
            try:
                await self._store(db, candidates, outcome, created_by=created_by)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        self._log_batch(len(events), outcome)
        return outcome.to_response()

    @staticmethod
    def _validate_batch_size(size: int) -> None:
        max_size = settings.TELEMETRY_MAX_BATCH_SIZE
        if size == 0:
            raise EmptyBatchError()
        if size > max_size:
            raise BatchTooLargeError(max_size)

    def _select_candidates(self, events: Sequence[Any], outcome: _BatchOutcome) -> dict[UUID, _Candidate]:
        """Validate each event and resolve repeats inside the batch (first one wins)."""
        candidates: dict[UUID, _Candidate] = {}
        closed_alerts: set[UUID] = set()

        for index, raw in enumerate(events):
            try:
                event = TelemetryEventIn.model_validate(raw)
            except ValidationError as exc:
                error = exc.errors()[0]
                outcome.reject(raw, error_field(error) or f"eventos[{index}]", error_message(error))
                continue

            first = candidates.get(event.evento_id)
            if first is not None:
                outcome.duplicates += 1
                _log_if_divergent(event, stored=first.payload, received=raw)
                continue

            if event.evento == ALERT_CLOSED_EVENT:
                if event.alerta_id in closed_alerts:
                    _reject_repeated_closure(outcome, raw, event)
                    continue
                closed_alerts.add(event.alerta_id)

            candidates[event.evento_id] = _Candidate(event=event, payload=raw)
        return candidates

    async def _store(
        self,
        db: AsyncSession,
        candidates: dict[UUID, _Candidate],
        outcome: _BatchOutcome,
        *,
        created_by: str,
    ) -> None:
        """Insert new events; classify the skipped ones as duplicate or repeated closure."""
        inserted = await self._repo.insert_new(
            db,
            events=[
                {
                    "evento_id": c.event.evento_id,
                    "evento": c.event.evento,
                    "alerta_id": c.event.alerta_id,
                    "payload": c.payload,
                }
                for c in candidates.values()
            ],
            created_by=created_by,
        )
        outcome.accepted += len(inserted)

        skipped = candidates.keys() - inserted
        stored = await self._repo.find_payloads(db, evento_ids=skipped)
        for evento_id in skipped:
            candidate = candidates[evento_id]
            if evento_id in stored:
                outcome.duplicates += 1
                _log_if_divergent(candidate.event, stored=stored[evento_id], received=candidate.payload)
            else:
                # Not stored under its own evento_id, so the closure index rejected it.
                _reject_repeated_closure(outcome, candidate.payload, candidate.event)

    @staticmethod
    def _log_batch(total: int, outcome: _BatchOutcome) -> None:
        _log(logging.INFO, {
            "event": "telemetria_lote_recebido",
            "total": total,
            "aceitos": outcome.accepted,
            "duplicados": outcome.duplicates,
            "rejeitados": [
                {"evento_id": r.evento_id, "campo": r.campo, "mensagem": r.mensagem}
                for r in outcome.rejected
            ],
        })


def _raw_evento_id(raw: Any) -> str | None:
    value = raw.get(_EVENTO_ID) if isinstance(raw, dict) else None
    return value if isinstance(value, str) else None


def _reject_repeated_closure(outcome: _BatchOutcome, raw: Any, event: TelemetryEventIn) -> None:
    outcome.reject(raw, _ALERTA_ID, messages.CLOSURE_ALREADY_RECORDED)
    _log(logging.WARNING, {
        "event": "telemetria_encerramento_repetido",
        "evento_id": str(event.evento_id),
        "alerta_id": str(event.alerta_id),
    })


def _log_if_divergent(event: TelemetryEventIn, *, stored: dict[str, Any], received: dict[str, Any]) -> None:
    """A repeated evento_id with different content points to a client bug.

    Logs only field names, never values: payloads may carry identifiers.
    """
    differing = sorted(k for k in stored.keys() | received.keys() if stored.get(k) != received.get(k))
    if differing:
        _log(logging.WARNING, {
            "event": "telemetria_duplicado_divergente",
            "evento_id": str(event.evento_id),
            "evento": event.evento,
            "campos_divergentes": differing,
        })


def _log(level: int, entry: dict[str, Any]) -> None:
    logger.log(level, orjson.dumps(entry).decode())
