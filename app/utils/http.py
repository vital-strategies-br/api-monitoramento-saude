from starlette.responses import JSONResponse
from starlette.types import Scope

from app.utils.text import sha256_hex

PUBLIC_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def is_public_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PATH_PREFIXES)


def is_public_request(method: str, path: str) -> bool:
    """CORS pre-flight and public paths skip auth, rate limit and body limit."""
    return method == "OPTIONS" or is_public_path(path)


def client_ip(scope: Scope) -> str:
    # Uvicorn already resolves X-Forwarded-For for proxies in FORWARDED_ALLOW_IPS.
    client = scope.get("client")
    return client[0] if client else ""


def error_response(status_code: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)


def api_key_fingerprint(api_key: str) -> str:
    """Stable, non-reversible reference to the calling client; never store the key itself."""
    return sha256_hex(api_key.encode("utf-8"))
