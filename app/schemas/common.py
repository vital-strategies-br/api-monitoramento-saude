from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Body of every error response: one human-readable text under `detail`."""

    detail: str = Field(
        ...,
        description="Mensagem de erro, sempre um único texto (nunca lista ou objeto).",
        examples=["Lote vazio: informe ao menos 1 evento"],
    )
