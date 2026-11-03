from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Alert(Base):
    __tablename__ = "alerta"
    __table_args__ = {"schema": "monitoramento"}

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    individuo_evento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("monitoramento.individuo_evento.id"),
        nullable=False, unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class AlertResponse(Base):
    __tablename__ = "alerta_resposta"
    __table_args__ = (
        Index("idx_alerta_resposta_alerta_data", "alerta_id", "served_at"),
        {"schema": "monitoramento"},
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    alerta_id: Mapped[UUID] = mapped_column(ForeignKey("monitoramento.alerta.id"))
    endpoint: Mapped[str] = mapped_column(Text)
    served_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    tipo_evento: Mapped[str] = mapped_column(Text)
    metodo_identificacao: Mapped[str] = mapped_column(Text)
    data_identificacao: Mapped[date] = mapped_column(Date)
    banco_origem_identificacao: Mapped[str | None] = mapped_column(Text)
    id_registro_identificacao: Mapped[str | None] = mapped_column(Text)


class AlertResponseIdentifier(Base):
    __tablename__ = "alerta_resposta_identificador"
    __table_args__ = (
        Index("idx_alerta_resposta_identificador_lookup",
              "tipo_identificador", "valor_identificador"),
        {"schema": "monitoramento"},
    )

    resposta_id: Mapped[UUID] = mapped_column(
        ForeignKey("monitoramento.alerta_resposta.id"), primary_key=True,
    )
    tipo_identificador: Mapped[str] = mapped_column(Text, primary_key=True)
    valor_identificador: Mapped[str] = mapped_column(Text, primary_key=True)
