import hashlib
import hmac
import logging
import time
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import orjson
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.telemetry import service
from app.core import messages
from app.core.config import settings
from app.core.rate_limit import rate_limiter
from app.db.session import get_db
from app.main import app
from app.schemas.telemetry import EXAMPLE_EVENT
from app.utils.http import api_key_fingerprint

SPEC_MAX_BATCH_SIZE = 200  # contract value from the specification (section 8.6)
PATH = "/api/v1/telemetria/eventos"
API_KEY = "test-api-key"
SECRET = "test-secret"


def make_event(**overrides):
    return {**EXAMPLE_EVENT, "evento_id": str(uuid4()), **overrides}


def make_closure(alerta_id):
    return make_event(evento="alerta_encerrado", alerta_id=alerta_id, motivo_encerramento="negou_explicitamente")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", API_KEY)
    monkeypatch.setattr(settings, "API_SECRET", SECRET)
    monkeypatch.setattr(settings, "REQUIRE_HMAC", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)
    rate_limiter.reset()

    async def insert_all(db, *, events, created_by):
        return {e["evento_id"] for e in events}

    monkeypatch.setattr(service._repo, "insert_new", AsyncMock(side_effect=insert_all))
    monkeypatch.setattr(service._repo, "find_payloads", AsyncMock(return_value={}))
    session = AsyncMock()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(db):
    return TestClient(app, raise_server_exceptions=False)


def send(client, body):
    return client.post(PATH, json=body, headers={"X-API-Key": API_KEY})


def counts_add_up(body, sent):
    return body["aceitos"] + body["duplicados"] + len(body["rejeitados"]) == sent


# --- envelope -----------------------------------------------------------------

@pytest.mark.parametrize("size", [1, 2, SPEC_MAX_BATCH_SIZE])
def test_valid_batch_is_stored_and_accepted(client, db, size):
    response = send(client, {"eventos": [make_event() for _ in range(size)]})
    assert response.status_code == 200
    assert response.json() == {"aceitos": size, "duplicados": 0, "rejeitados": []}
    stored = service._repo.insert_new.call_args.kwargs
    assert len(stored["events"]) == size
    assert stored["created_by"] == api_key_fingerprint(API_KEY)
    db.commit.assert_awaited_once()


def test_empty_batch_returns_spec_message(client):
    response = send(client, {"eventos": []})
    assert response.status_code == 422
    assert response.json() == {"detail": "Lote vazio: informe ao menos 1 evento"}


def test_batch_over_limit_returns_413_stating_maximum(client):
    response = send(client, {"eventos": [make_event() for _ in range(SPEC_MAX_BATCH_SIZE + 1)]})
    assert response.status_code == 413
    assert response.json() == {
        "detail": messages.BATCH_TOO_LARGE.format(max_eventos=SPEC_MAX_BATCH_SIZE),
    }


def test_default_batch_limit_matches_contract():
    assert type(settings).model_fields["TELEMETRY_MAX_BATCH_SIZE"].default == SPEC_MAX_BATCH_SIZE


def test_batch_limit_is_configurable(client, monkeypatch):
    monkeypatch.setattr(settings, "TELEMETRY_MAX_BATCH_SIZE", 3)
    assert send(client, {"eventos": [make_event() for _ in range(3)]}).status_code == 200
    response = send(client, {"eventos": [make_event() for _ in range(4)]})
    assert response.status_code == 413
    assert "3" in response.json()["detail"]


@pytest.mark.parametrize("body, detail", [
    ({}, "eventos: campo obrigatório ausente"),
    ({"eventos": None}, "eventos: valor deve ser uma lista"),
    ({"eventos": "x"}, "eventos: valor deve ser uma lista"),
    ([], "valor deve ser um objeto JSON"),
])
def test_invalid_envelope_returns_422_with_string_detail(client, body, detail):
    response = send(client, body)
    assert response.status_code == 422
    assert response.json() == {"detail": detail}


def test_malformed_json_returns_422_with_string_detail(client):
    response = client.post(
        PATH, content=b"{not json",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "JSON malformado"}


# --- per-event validation -----------------------------------------------------

@pytest.mark.parametrize("event, evento_id, campo, mensagem", [
    (1, None, "eventos[0]", "valor deve ser um objeto JSON"),
    ({"evento": "alerta_exibido"}, None, "evento_id", "campo obrigatório ausente"),
    ({**EXAMPLE_EVENT, "evento_id": "abc"}, "abc", "evento_id", "valor não é um UUID válido"),
    ({**EXAMPLE_EVENT, "alerta_id": "x"}, EXAMPLE_EVENT["evento_id"], "alerta_id", "valor não é um UUID válido"),
    ({**EXAMPLE_EVENT, "evento": "outro"}, EXAMPLE_EVENT["evento_id"], "evento", "valor não permitido"),
    ({**EXAMPLE_EVENT, "paciente_id": "1"}, EXAMPLE_EVENT["evento_id"], "paciente_id", "campo não permitido"),
    ({**EXAMPLE_EVENT, "evento_id": 7}, None, "evento_id", "valor não é um UUID válido"),
])
def test_invalid_event_is_rejected_without_failing_batch(client, event, evento_id, campo, mensagem):
    response = send(client, {"eventos": [event, make_event()]})
    assert response.status_code == 200
    body = response.json()
    assert body["aceitos"] == 1
    assert body["rejeitados"] == [{"evento_id": evento_id, "campo": campo, "mensagem": mensagem}]


def test_all_rejected_batch_does_not_touch_database(client, db):
    response = send(client, {"eventos": [1, {}]})
    assert response.status_code == 200
    assert len(response.json()["rejeitados"]) == 2
    service._repo.insert_new.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_counts_always_add_up(client):
    repeated = make_event()
    alerta = str(uuid4())
    events = [
        repeated, dict(repeated), make_event(), 1, {**EXAMPLE_EVENT, "alerta_tipo": "x"},
        make_closure(alerta), make_closure(alerta),
    ]
    response = send(client, {"eventos": events})
    body = response.json()
    assert counts_add_up(body, len(events))
    assert (body["aceitos"], body["duplicados"], len(body["rejeitados"])) == (3, 1, 3)


# --- duplicates (item 6) ------------------------------------------------------

def test_repeated_evento_id_in_batch_counts_as_duplicate(client, caplog):
    event = make_event()
    with caplog.at_level(logging.WARNING, logger="app.telemetria"):
        response = send(client, {"eventos": [event, dict(event)]})
    assert response.json() == {"aceitos": 1, "duplicados": 1, "rejeitados": []}
    assert "telemetria_duplicado_divergente" not in caplog.text


def test_divergent_duplicate_in_batch_is_logged_without_values(client, caplog):
    event = make_event()
    with caplog.at_level(logging.WARNING, logger="app.telemetria"):
        response = send(client, {"eventos": [event, {**event, "unidade_cnes": "9999999"}]})
    assert response.json()["duplicados"] == 1
    assert "telemetria_duplicado_divergente" in caplog.text
    assert '"campos_divergentes":["unidade_cnes"]' in caplog.text
    assert "9999999" not in caplog.text


def test_evento_id_stored_in_earlier_batch_counts_as_duplicate(client, caplog):
    event = make_event()
    service._repo.insert_new.side_effect = None
    service._repo.insert_new.return_value = set()
    service._repo.find_payloads.return_value = {
        UUID(event["evento_id"]): {**event, "plugin_versao": "0.9.0"},
    }
    with caplog.at_level(logging.WARNING, logger="app.telemetria"):
        response = send(client, {"eventos": [event]})
    assert response.json() == {"aceitos": 0, "duplicados": 1, "rejeitados": []}
    assert '"campos_divergentes":["plugin_versao"]' in caplog.text


# --- one closure per alert (item 13) ------------------------------------------

def test_second_closure_in_same_batch_is_rejected(client, caplog):
    alerta = str(uuid4())
    first, second = make_closure(alerta), make_closure(alerta)
    with caplog.at_level(logging.WARNING, logger="app.telemetria"):
        response = send(client, {"eventos": [first, second]})
    assert response.json() == {
        "aceitos": 1,
        "duplicados": 0,
        "rejeitados": [{
            "evento_id": second["evento_id"],
            "campo": "alerta_id",
            "mensagem": messages.CLOSURE_ALREADY_RECORDED,
        }],
    }
    assert "telemetria_encerramento_repetido" in caplog.text


def test_closure_for_alert_closed_in_earlier_batch_is_rejected(client):
    closure = make_closure(str(uuid4()))
    service._repo.insert_new.side_effect = None
    service._repo.insert_new.return_value = set()  # skipped by the closure unique index
    response = send(client, {"eventos": [closure]})
    assert response.json()["rejeitados"] == [{
        "evento_id": closure["evento_id"],
        "campo": "alerta_id",
        "mensagem": messages.CLOSURE_ALREADY_RECORDED,
    }]


def test_closures_for_different_alerts_are_accepted(client):
    response = send(client, {"eventos": [make_closure(str(uuid4())), make_closure(str(uuid4()))]})
    assert response.json()["aceitos"] == 2


# --- storage failure and auth -------------------------------------------------

def test_storage_failure_returns_500_and_rolls_back(client, db):
    service._repo.insert_new.side_effect = RuntimeError("database unavailable")
    response = send(client, {"eventos": [make_event()]})
    assert response.status_code == 500
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


def test_missing_api_key_returns_401(client):
    assert client.post(PATH, json={"eventos": [make_event()]}).status_code == 401


@pytest.mark.parametrize("valid_signature", [True, False])
def test_route_is_protected_by_hmac(client, monkeypatch, valid_signature):
    monkeypatch.setattr(settings, "REQUIRE_HMAC", True)
    body = orjson.dumps({"eventos": [make_event()]})
    ts = str(int(time.time()))
    signing = "\n".join([ts, "POST", PATH, "", hashlib.sha256(body).hexdigest()])
    signature = hmac.new(SECRET.encode(), signing.encode(), hashlib.sha256).hexdigest()
    response = client.post(PATH, content=body, headers={
        "X-API-Key": API_KEY,
        "X-Timestamp": ts,
        "X-Signature": signature if valid_signature else "0" * 64,
        "Content-Type": "application/json",
    })
    assert response.status_code == (200 if valid_signature else 401)
