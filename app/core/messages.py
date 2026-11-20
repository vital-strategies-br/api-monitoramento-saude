"""Client-facing messages: the single source for runtime responses and Swagger examples.

Every error body is {"detail": "<one of these texts>"}; per-event rejections use
the same texts in `rejeitados[].mensagem`. Telemetry texts are Portuguese, as in
the Alert Plugin Final Specification. Limits are interpolated from settings,
never written into the text.
"""

# --- Request-level errors (`detail`) ------------------------------------------
EMPTY_BATCH = "Lote vazio: informe ao menos 1 evento"
BATCH_TOO_LARGE = "Lote acima do limite: envie no máximo {max_eventos} eventos por chamada"
BODY_TOO_LARGE = "Corpo da requisição acima do limite: envie no máximo {max_bytes} bytes por chamada"
BODY_MISSING = "corpo da requisição ausente"
RATE_LIMITED = "Limite de requisições excedido: tente novamente em {segundos} segundos"
INTERNAL_ERROR = "Erro interno"

# Authentication (ApiAuthMiddleware). Kept in English: the alert query API
# already returns these texts in production, so changing them changes its contract.
UNAUTHORIZED = "Unauthorized"
TIMESTAMP_INVALID = "Missing/invalid X-Timestamp"
TIMESTAMP_STALE = "Stale request"
SIGNATURE_MISSING = "Missing signature/secret"
SIGNATURE_INVALID = "Invalid signature"
ORIGIN_NOT_ALLOWED = "Origin not allowed"

# --- Per-event rejections (`rejeitados[].mensagem`) ---------------------------
CLOSURE_ALREADY_RECORDED = "alerta_encerrado já registrado para este alerta_id"
FORBIDDEN_FIELD = "campo não permitido"
NULL_VALUE = "valor nulo não permitido"
INVALID_TEXT = "texto com caractere não permitido (\\u0000 ou Unicode inválido)"
INVALID_NUMBER = "número não permitido (NaN, Infinity ou fora do intervalo)"
UNSTORABLE_EVENT = "evento contém valor que o banco de dados não aceita"
INVALID_VALUE = "valor inválido"

# Error types raised by our own validators: their message is already one of the texts above.
FORBIDDEN_FIELD_ERROR = "campo_proibido"
UNSTORABLE_VALUE_ERROR = "valor_nao_armazenavel"
OWN_ERROR_TYPES = frozenset({FORBIDDEN_FIELD_ERROR, UNSTORABLE_VALUE_ERROR})

# Pydantic error type -> message. Any other Pydantic type falls back to INVALID_VALUE,
# so no English text from the library reaches the client.
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

# Every text an event rejection can carry, in a stable order (documented in Swagger).
REJECTION_MESSAGES = tuple(dict.fromkeys([
    VALIDATION_ERRORS["missing"],
    NULL_VALUE,
    VALIDATION_ERRORS["uuid_parsing"],
    VALIDATION_ERRORS["literal_error"],
    VALIDATION_ERRORS["model_type"],
    FORBIDDEN_FIELD,
    INVALID_TEXT,
    INVALID_NUMBER,
    CLOSURE_ALREADY_RECORDED,
    UNSTORABLE_EVENT,
    INVALID_VALUE,
]))
