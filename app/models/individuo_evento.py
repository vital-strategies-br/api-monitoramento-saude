from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    Enum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


MetodoIdentificacaoEnum = Enum(
    "n_a",
    "modelo_semantica_explicita",
    "modelo_classificacao_provavel",
    name="metodo_identificacao_enum",
    schema="monitoramento",
)

BancoOrigemIdentificacaoEnum = Enum(
    "e-SUS APS",
    name="banco_origem_identificacao_enum",
    schema="monitoramento",
)


class IndividuoEvento(Base):
    __tablename__ = "individuo_evento"
    __table_args__ = (
        Index("idx_individuo_evento_lookup", "individuo_id", "tipo_evento"),
        CheckConstraint(
            """
            (id_registro_identificacao IS NULL AND banco_origem_identificacao IS NULL)
            OR
            (id_registro_identificacao IS NOT NULL AND banco_origem_identificacao IS NOT NULL)
            """,
            name="individuo_evento_identificacao_origem_chk",
        ),
        Index(
            "ux_individuo_evento_origem_metodo",
            "individuo_id",
            "tipo_evento",
            "metodo_identificacao",
            "banco_origem_identificacao",
            "id_registro_identificacao",
            unique=True,
            postgresql_where=(
                "id_registro_identificacao IS NOT NULL "
                "AND banco_origem_identificacao IS NOT NULL"
            ),
        ),
        {"schema": "monitoramento"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    individuo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("monitoramento.individuo.id", ondelete="CASCADE"),
        nullable=False,
    )

    tipo_evento: Mapped[str] = mapped_column(Text, nullable=False)

    data_identificacao: Mapped[object] = mapped_column(Date, nullable=False)

    metodo_identificacao: Mapped[str] = mapped_column(
        MetodoIdentificacaoEnum,
        nullable=False,
        server_default="n_a",
    )

    banco_origem_identificacao: Mapped[str | None] = mapped_column(
        BancoOrigemIdentificacaoEnum,
        nullable=True,
    )

    id_registro_identificacao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
