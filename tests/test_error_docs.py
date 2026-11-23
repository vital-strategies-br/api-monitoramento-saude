"""Every error example documented in Swagger is exactly what the API returns."""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import orjson
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.telemetry import service
from app.core.config import settings
from app.db.session import get_db
from app.main import app

PATH = "/api/v1/telemetria/eventos"
API_KEY = "test-api-key"
SECRET = "test-secret"
ALERTA = "3f6c2a1e-8b4d-4c2f-9a7e-1d2b3c4d5e6f"


@pytest.fixture(scope="module")
def openapi():
    return app.openapi()


def documented(openapi, status, path=PATH):
    """{example name: example body} for one documented response."""
    content = openapi["paths"][path]["post"]["responses"][str(status)]["content"]["application/json"]
    return {name: ex["value"] for name, ex in content["examples"].items()}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", API_KEY)
    monkeypatch.setattr(settings, "API_SECRET", SECRET)
    monkeypatch.setattr(settings, "REQUIRE_HMAC", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)

    async def insert_all(db, *, events, created_by):
        return {e["evento_id"] for e in events}

    monkeypatch.setattr(service._repo, "insert_new", AsyncMock(side_effect=insert_all))
    monkeypatch.setattr(service._repo, "find_payloads", AsyncMock(return_value={}))

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def ev(**fields):
    return {"evento_id": str(uuid4()), "evento": "alerta_aberto", "alerta_id": ALERTA, **fields}


def post(client, body: bytes, **headers):
    return client.post(PATH, content=body, headers={
        "X-API-Key": API_KEY, "Content-Type": "application/json", **headers,
    })


def signed_headers(body: bytes, *, ts: int, signature: str | None = None) -> dict[str, str]:
    signing = "\n".join([str(ts), "POST", PATH, "", hashlib.sha256(body).hexdigest()])
    computed = hmac.new(SECRET.encode(), signing.encode(), hashlib.sha256).hexdigest()
    return {"X-Timestamp": str(ts), "X-Signature": signature or computed}


# --- every 4xx/5xx body is the documented {"detail": "<text>"} ---------------

REQUESTS_422 = {
    "lote_vazio": b'{"eventos": []}',
    "corpo_ausente": b"null",
    "json_malformado": b"{",
    "corpo_nao_objeto": b"[]",
    "eventos_ausente": b"{}",
    "eventos_nulo": b'{"eventos": null}',
    "eventos_nao_lista": b'{"eventos": "x"}',
}


def test_every_documented_422_is_returned(client, openapi):
    examples = documented(openapi, 422)
    assert examples.keys() == REQUESTS_422.keys()
    for name, body in REQUESTS_422.items():
        response = post(client, body)
        assert (response.status_code, response.json()) == (422, examples[name]), name


def test_documented_413_for_events(client, openapi):
    body = orjson.dumps({"eventos": [ev() for _ in range(settings.TELEMETRY_MAX_BATCH_SIZE + 1)]})
    response = post(client, body)
    assert (response.status_code, response.json()) == (413, documented(openapi, 413)["eventos"])


def test_documented_413_for_bytes(client, openapi):
    response = post(client, b"x" * (settings.MAX_REQUEST_BODY_BYTES + 1))
    assert (response.status_code, response.json()) == (413, documented(openapi, 413)["bytes"])


def test_documented_401s(client, openapi, monkeypatch):
    examples = documented(openapi, 401)
    body = orjson.dumps({"eventos": [ev()]})

    response = client.post(PATH, content=body, headers={"Content-Type": "application/json"})
    assert response.json() == examples["api_key"]

    monkeypatch.setattr(settings, "REQUIRE_HMAC", True)
    now = int(time.time())
    cases = {
        "timestamp_invalido": {"X-Timestamp": "abc"},
        "timestamp_expirado": signed_headers(body, ts=now - settings.TIMESTAMP_TOLERANCE_SECONDS - 60),
        "assinatura_ausente": {"X-Timestamp": str(now)},
        "assinatura_invalida": signed_headers(body, ts=now, signature="0" * 64),
    }
    for name, headers in cases.items():
        response = post(client, body, **headers)
        assert (response.status_code, response.json()) == (401, examples[name]), name


def test_documented_403(client, openapi, monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", True)
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "chrome-extension://permitida")
    response = post(client, orjson.dumps({"eventos": [ev()]}), Origin="https://outra.example")
    assert (response.status_code, response.json()) == (403, documented(openapi, 403)["origem"])


def test_documented_429_has_retry_after(client, openapi, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_REQUESTS", 1)
    body = orjson.dumps({"eventos": [ev()]})
    post(client, body)
    response = post(client, body)
    assert response.status_code == 429
    doc = openapi["paths"][PATH]["post"]["responses"]["429"]
    assert "Retry-After" in doc["headers"]
    seconds = response.headers["Retry-After"]
    documented_text = documented(openapi, 429)["limite"]["detail"]
    assert response.json()["detail"] == documented_text.replace(
        str(settings.RATE_LIMIT_WINDOW_SECONDS), seconds,
    )


def test_documented_500(client, openapi):
    service._repo.insert_new.side_effect = RuntimeError("database unavailable")
    response = post(client, orjson.dumps({"eventos": [ev()]}))
    assert (response.status_code, response.json()) == (500, documented(openapi, 500)["erro_interno"])


# --- the 200 "one of each rejection" example is reproducible ------------------

def test_documented_rejections_example_is_reproducible(client, openapi):
    example = documented(openapi, 200)["rejeicoes"]
    closure = ev(evento="alerta_encerrado", alerta_id=str(uuid4()))
    events = [
        orjson.dumps({"evento": "alerta_aberto", "alerta_id": ALERTA}),
        orjson.dumps(ev(alerta_id=None)),
        orjson.dumps(ev(alerta_id="x")),
        orjson.dumps(ev(evento="outro")),
        b"1",
        b"null",
        orjson.dumps(ev(paciente_id="1")),
        orjson.dumps(ev(extra={"lista": ["ok", "\x00"]})),
        orjson.dumps(ev())[:-1] + b', "etapa": NaN}',
        orjson.dumps(closure),
        orjson.dumps({**closure, "evento_id": str(uuid4())}),
    ]
    response = post(client, b'{"eventos": [' + b", ".join(events) + b"]}")
    body = response.json()

    def shape(rejections):
        return [(r["campo"], r["mensagem"], r["evento_id"] is None) for r in rejections]

    assert (body["aceitos"], body["duplicados"]) == (example["aceitos"], example["duplicados"])
    assert shape(body["rejeitados"]) == shape(example["rejeitados"])


# --- error bodies are always one string ---------------------------------------

def test_error_schema_is_a_single_string(openapi):
    schema = openapi["components"]["schemas"]["ErrorDetail"]
    assert schema["required"] == ["detail"]
    assert schema["properties"]["detail"]["type"] == "string"
    responses = openapi["paths"][PATH]["post"]["responses"]
    for status in ("401", "403", "413", "422", "429", "500"):
        ref = responses[status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorDetail"), status
