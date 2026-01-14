import hashlib
import hmac
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import _normalize_timestamp
from app.core.auth import ApiAuthMiddleware
from app.core.config import settings


def _build_signature(*, secret: str, ts: int, method: str, path: str, query: str, body: bytes) -> str:
    body_hash_hex = hashlib.sha256(body).hexdigest()
    signing_string = "\n".join([str(ts), method.upper(), path, query, body_hash_hex])
    return hmac.new(secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256).hexdigest()


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiAuthMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/v1/echo")
    async def echo(payload: dict):
        return payload

    return app


def _configure_settings(*, require_hmac: bool = True) -> None:
    settings.API_KEYS = "test-api-key"
    settings.API_SECRET = "test-secret"
    settings.REQUIRE_HMAC = require_hmac
    settings.TIMESTAMP_TOLERANCE_SECONDS = 120
    settings.ENFORCE_ORIGIN_CHECK = False


def test_normalize_timestamp_accepts_milliseconds() -> None:
    ts_s = 1_736_860_800
    ts_ms = ts_s * 1000
    assert _normalize_timestamp(str(ts_s)) == ts_s
    assert _normalize_timestamp(str(ts_ms)) == ts_s


def test_exempt_paths_do_not_require_auth() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_missing_api_key_is_rejected() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    r = client.post("/api/v1/echo", json={"ok": True})
    assert r.status_code == 401


def test_hmac_required_missing_timestamp_is_rejected() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    r = client.post(
        "/api/v1/echo",
        json={"ok": True},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 401
    assert r.json().get("detail") == "Missing/invalid X-Timestamp"


def test_hmac_required_stale_timestamp_is_rejected() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    ts = int(time.time()) - (settings.TIMESTAMP_TOLERANCE_SECONDS + 10)
    body = b'{"ok":true}'
    sig = _build_signature(
        secret=settings.API_SECRET,
        ts=ts,
        method="POST",
        path="/api/v1/echo",
        query="",
        body=body,
    )

    r = client.post(
        "/api/v1/echo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key",
            "X-Timestamp": str(ts),
            "X-Signature": sig,
        },
    )
    assert r.status_code == 401
    assert r.json().get("detail") == "Stale request"


def test_hmac_required_invalid_signature_is_rejected() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    ts = int(time.time())
    body = b'{"ok":true}'
    bad_sig = "0" * 64

    r = client.post(
        "/api/v1/echo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key",
            "X-Timestamp": str(ts),
            "X-Signature": bad_sig,
        },
    )
    assert r.status_code == 401
    assert r.json().get("detail") == "Invalid signature"


def test_hmac_required_valid_signature_is_accepted() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    ts = int(time.time())
    body = b'{"ok":true}'
    sig = _build_signature(
        secret=settings.API_SECRET,
        ts=ts,
        method="POST",
        path="/api/v1/echo",
        query="",
        body=body,
    )

    r = client.post(
        "/api/v1/echo",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key",
            "X-Timestamp": str(ts),
            "X-Signature": sig,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_hmac_includes_query_string_in_signature() -> None:
    _configure_settings(require_hmac=True)
    client = TestClient(_make_app())

    ts = int(time.time())
    body = b'{"ok":true}'
    sig = _build_signature(
        secret=settings.API_SECRET,
        ts=ts,
        method="POST",
        path="/api/v1/echo",
        query="foo=bar",
        body=body,
    )

    r = client.post(
        "/api/v1/echo?foo=bar",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": "test-api-key",
            "X-Timestamp": str(ts),
            "X-Signature": sig,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_hmac_can_be_disabled_via_settings() -> None:
    _configure_settings(require_hmac=False)
    client = TestClient(_make_app())

    r = client.post(
        "/api/v1/echo",
        json={"ok": True},
        headers={"X-API-Key": "test-api-key"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
