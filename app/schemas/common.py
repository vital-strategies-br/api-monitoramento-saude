from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    detail: str = Field(..., description="Mensagem de erro.")
