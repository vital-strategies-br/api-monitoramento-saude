import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import messages
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.config import settings
from app.core.rate_limit import FixedWindowRateLimiter, RateLimitMiddleware, rate_limiter
from app.main import app as real_app

LIMIT_BYTES = 64
TEST_CLIENT_IP = "testclient"  # what Starlette's TestClient reports as the client host


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/v1/echo")
    async def echo(request: Request):
        return {"bytes": len(await request.body())}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", LIMIT_BYTES)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    rate_limiter.reset()
    return TestClient(_make_app())


def too_large_detail():
    return {"detail": messages.BODY_TOO_LARGE.format(max_bytes=LIMIT_BYTES)}


# --- body size (item 9) -------------------------------------------------------

def test_body_within_limit_reaches_route_intact(client):
    response = client.post("/api/v1/echo", content=b"x" * LIMIT_BYTES)
    assert response.status_code == 200
    assert response.json() == {"bytes": LIMIT_BYTES}


def test_declared_content_length_over_limit_returns_413(client):
    response = client.post("/api/v1/echo", content=b"x" * (LIMIT_BYTES + 1))
    assert response.status_code == 413
    assert response.json() == too_large_detail()


def test_chunked_body_over_limit_returns_413(client):
    chunks = (b"x" * (LIMIT_BYTES // 2) for _ in range(3))
    response = client.post("/api/v1/echo", content=chunks)
    assert response.status_code == 413
    assert response.json() == too_large_detail()


def test_body_limit_runs_before_authentication(monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", LIMIT_BYTES)
    response = TestClient(real_app).post(
        "/api/v1/telemetria/eventos", content=b"x" * (LIMIT_BYTES + 1),
    )
    assert response.status_code == 413  # not 401: the body is never read by auth


# --- rate limit (items 8 and 12) ----------------------------------------------

def enable_rate_limit(monkeypatch, *, requests=2, exempt=""):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", requests)
    monkeypatch.setattr(settings, "RATE_LIMIT_EXEMPT_IPS", exempt)


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    enable_rate_limit(monkeypatch)
    statuses = [client.post("/api/v1/echo").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
    response = client.post("/api/v1/echo")
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= settings.RATE_LIMIT_WINDOW_SECONDS
    assert response.json() == {"detail": messages.RATE_LIMITED.format(segundos=retry_after)}


def test_exempt_ip_is_never_limited(client, monkeypatch):
    enable_rate_limit(monkeypatch, exempt=f"10.0.0.1, {TEST_CLIENT_IP}")
    assert all(client.post("/api/v1/echo").status_code == 200 for _ in range(5))


def test_rate_limit_disabled_by_default(client):
    assert type(settings).model_fields["RATE_LIMIT_ENABLED"].default is False
    assert all(client.post("/api/v1/echo").status_code == 200 for _ in range(5))


def test_public_paths_are_not_limited(client, monkeypatch):
    enable_rate_limit(monkeypatch, requests=1)
    assert all(client.get("/health").status_code == 200 for _ in range(3))


def test_limiter_counts_per_client_and_resets_each_window():
    limiter = FixedWindowRateLimiter()
    hit = lambda client, now: limiter.hit(client, limit=1, window_seconds=60, now=now)
    assert hit("a", 0) is None
    assert hit("b", 1) is None
    assert hit("a", 50) == 10
    assert hit("a", 60) is None  # new window
