from sqlalchemy import BigInteger, Date, DateTime, PrimaryKeyConstraint, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricasDiariasEndpoint(Base):
    __tablename__ = "metricas_diarias_endpoint"
    __table_args__ = (
        PrimaryKeyConstraint("endpoint", "tipo_evento", "data"),
        {"schema": "monitoramento"},
    )

    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_evento: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[object] = mapped_column(Date, nullable=False)
    total_chamadas: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    respostas_positivas: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metodo_identificacao: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
