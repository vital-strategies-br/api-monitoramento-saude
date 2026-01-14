from fastapi import Security, HTTPException
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def swagger_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    return api_key
