import hmac
import time
import hashlib
from http import HTTPStatus
from typing import Iterable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import messages
from app.core.config import settings
from app.utils.http import error_response, is_public_request
from app.utils.text import sha256_hex


def _normalize_timestamp(ts_raw: str) -> Optional[int]:
    try:
        ts_int = int(ts_raw)
    except Exception:
        return None

    # heuristic: ms timestamps are usually >= 1e12
    if ts_int >= 1_000_000_000_000:
        ts_int = ts_int // 1000
    return ts_int


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
        # 0-1) Skip pre-flight and public paths
        if is_public_request(request.method, request.url.path):
            return await call_next(request)

        # 2) Origin validation (complements CORS; easy to disable via env)
        if settings.ENFORCE_ORIGIN_CHECK:
            origin = request.headers.get("origin")
            allowed = set(settings.allowed_origins_list())

            if origin and allowed and origin not in allowed:
                return error_response(HTTPStatus.FORBIDDEN, messages.ORIGIN_NOT_ALLOWED)

        # 3) API key (header)
        api_key = request.headers.get("x-api-key")
        valid_keys: Iterable[str] = settings.api_keys_list()
        if not api_key or api_key not in valid_keys:
            return error_response(HTTPStatus.UNAUTHORIZED, messages.UNAUTHORIZED)
        
        # 4) Decide whether HMAC is required
        if not settings.hmac_required:
            return await call_next(request)

        # 5) Timestamp (anti-replay)
        ts_raw = request.headers.get("x-timestamp")
        ts_seconds = _normalize_timestamp(ts_raw) if ts_raw else None
        if ts_seconds is None:
            return error_response(HTTPStatus.UNAUTHORIZED, messages.TIMESTAMP_INVALID)

        now = int(time.time())
        if abs(now - ts_seconds) > settings.TIMESTAMP_TOLERANCE_SECONDS:
            return error_response(HTTPStatus.UNAUTHORIZED, messages.TIMESTAMP_STALE)

        # 6) Body hash
        body_bytes = await request.body()
        body_hash = sha256_hex(body_bytes)

        # 7) HMAC signature
        signature = request.headers.get("x-signature")
        if not signature or not settings.API_SECRET:
            return error_response(HTTPStatus.UNAUTHORIZED, messages.SIGNATURE_MISSING)

        signing_string = _build_signing_string(request, ts_seconds, body_hash)
        expected = _compute_hmac_hex(settings.API_SECRET, signing_string)

        if not hmac.compare_digest(signature, expected):
            return error_response(HTTPStatus.UNAUTHORIZED, messages.SIGNATURE_INVALID)

        return await call_next(request)
