from fastapi import Header, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def swagger_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    return api_key


def swagger_hmac_headers(
    x_timestamp: str | None = Header(
        None,
        alias="X-Timestamp",
        description=(
            "Timestamp Unix (em segundos ou milissegundos) usado para evitar replay. "
            "Obrigatório quando a API estiver com HMAC habilitado (ex.: `ENV=prod` ou `REQUIRE_HMAC=true`)."
        ),
        examples=[{"value": "1736860800"}, {"value": "1736860800000"}],
    ),
    x_signature: str | None = Header(
        None,
        alias="X-Signature",
        description=(
            "Assinatura HMAC-SHA256 em hexadecimal. A string assinada é: `timestamp\\nMETHOD\\nPATH\\nQUERY\\nsha256(body)` "
            "(query pode ser vazio)."
        ),
        examples=[{"value": "e3b0c44298fc1c149afbf4c8996fb924..."}],
    ),
) -> None:
    _ = (x_timestamp, x_signature)
    return None
