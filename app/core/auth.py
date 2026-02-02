import hmac
import time
import hashlib
from typing import Iterable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings


EXEMPT_PATH_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _is_exempt_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in EXEMPT_PATH_PREFIXES)


def _normalize_timestamp(ts_raw: str) -> Optional[int]:
    try:
        ts_int = int(ts_raw)
    except Exception:
        return None

    # heuristic: ms timestamps are usually >= 1e12
    if ts_int >= 1_000_000_000_000:
        ts_int = ts_int // 1000
    return ts_int


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_signing_string(request: Request, ts_seconds: int, body_hash_hex: str) -> str:
    query = request.url.query
    path = request.url.path
    method = request.method.upper()

    return "\n".join([str(ts_seconds), method, path, query, body_hash_hex])


def _compute_hmac_hex(secret: str, signing_string: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # 0) Ignorar pre-flight
        if request.method == "OPTIONS":
            return await call_next(request)

        # 1) Exceções
        if _is_exempt_path(request.url.path):
            return await call_next(request)

        # 2) Validação de origem (complementa CORS; fácil desligar por env)
        if settings.ENFORCE_ORIGIN_CHECK:
            origin = request.headers.get("origin")
            allowed = set(settings.allowed_origins_list())

            if origin and allowed and origin not in allowed:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)

        # 3) API key (header)
        api_key = request.headers.get("x-api-key")
        valid_keys: Iterable[str] = settings.api_keys_list()
        if not api_key or api_key not in valid_keys:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        
        # 4) Decide se exige HMAC
        if not settings.hmac_required:
            return await call_next(request)

        # 5) Timestamp (anti-replay)
        ts_raw = request.headers.get("x-timestamp")
        ts_seconds = _normalize_timestamp(ts_raw) if ts_raw else None
        if ts_seconds is None:
            return JSONResponse({"detail": "Missing/invalid X-Timestamp"}, status_code=401)

        now = int(time.time())
        if abs(now - ts_seconds) > settings.TIMESTAMP_TOLERANCE_SECONDS:
            return JSONResponse({"detail": "Stale request"}, status_code=401)

        # 6) Body hash
        body_bytes = await request.body()
        body_hash = _sha256_hex(body_bytes)

        # 7) Assinatura HMAC
        signature = request.headers.get("x-signature")
        if not signature or not settings.API_SECRET:
            return JSONResponse({"detail": "Missing signature/secret"}, status_code=401)

        signing_string = _build_signing_string(request, ts_seconds, body_hash)
        expected = _compute_hmac_hex(settings.API_SECRET, signing_string)

        if not hmac.compare_digest(signature, expected):
            return JSONResponse({"detail": "Invalid signature"}, status_code=401)

        return await call_next(request)
