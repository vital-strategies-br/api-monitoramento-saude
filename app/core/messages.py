"""Client-facing messages (Portuguese, as in the Alert Plugin Final Specification).

Single source for runtime responses and the Swagger examples, so they never drift.
Limits are interpolated from settings, never written into the text.
"""

EMPTY_BATCH = "Lote vazio: informe ao menos 1 evento"
BATCH_TOO_LARGE = "Lote acima do limite: envie no máximo {max_eventos} eventos por chamada"
BODY_TOO_LARGE = "Corpo da requisição acima do limite: envie no máximo {max_bytes} bytes por chamada"
RATE_LIMITED = "Limite de requisições excedido: tente novamente em {segundos} segundos"
CLOSURE_ALREADY_RECORDED = "alerta_encerrado já registrado para este alerta_id"
FORBIDDEN_FIELD = "campo não permitido"

# Pydantic error type -> message. Unknown types fall back to Pydantic's own text.
VALIDATION_ERRORS = {
    "missing": "campo obrigatório ausente",
    "uuid_parsing": "valor não é um UUID válido",
    "uuid_type": "valor não é um UUID válido",
    "literal_error": "valor não permitido",
    "string_type": "valor deve ser texto",
    "list_type": "valor deve ser uma lista",
    "model_type": "valor deve ser um objeto JSON",
    "model_attributes_type": "valor deve ser um objeto JSON",
    "dict_type": "valor deve ser um objeto JSON",
    "json_invalid": "JSON malformado",
    "json_type": "JSON malformado",
}
