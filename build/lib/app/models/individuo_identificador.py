from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IndividuoIdentificador(Base):
    __tablename__ = "individuo_identificador"
    __table_args__ = (
        Index(
            "idx_individuo_identificador_lookup",
            "tipo_identificador",
            "valor_identificador",
        ),
        {"schema": "monitoramento"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    individuo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("monitoramento.individuo.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo_identificador: Mapped[str] = mapped_column(Text, nullable=False)
    valor_identificador: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
