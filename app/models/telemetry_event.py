from typing import Any
from uuid import UUID

from sqlalchemy import Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditBase

ALERT_CLOSED_EVENT = "alerta_encerrado"


class TelemetryEvent(AuditBase):
    """One dashboard event sent by the plugin backend, stored as received."""

    __tablename__ = "telemetria_evento"
    __table_args__ = (
        Index("idx_telemetria_evento_alerta", "alerta_id"),
        # Spec CE-7: an alert is closed once. A second closure is rejected.
        Index(
            "uq_telemetria_evento_alerta_encerrado", "alerta_id",
            unique=True, postgresql_where=text(f"evento = '{ALERT_CLOSED_EVENT}'"),
        ),
        {"schema": "monitoramento"},
    )

    evento_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True)
    evento: Mapped[str] = mapped_column(Text, nullable=False)
    # No foreign key: an unknown alerta_id is not a reason to reject (spec 8.6).
    alerta_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
