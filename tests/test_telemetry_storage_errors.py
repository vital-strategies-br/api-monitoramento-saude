"""A value PostgreSQL refuses (DataError) rejects only that event, never the batch."""

import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError, OperationalError

from app.api.v1.endpoints.telemetry import service
from app.core import messages
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.schemas.telemetry import EXAMPLE_EVENT

PATH = "/api/v1/telemetria/eventos"
API_KEY = "test-api-key"
REFUSED_MARK = "refused-by-postgres"


class UntranslatableCharacter(Exception):
    """Stands in for the psycopg error class wrapped by SQLAlchemy's DataError."""


def make_event(**fields):
    return {**EXAMPLE_EVENT, "evento_id": str(uuid4()), **fields}


def refused(**fields):
    return make_event(extra=REFUSED_MARK, **fields)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", API_KEY)
    monkeypatch.setattr(settings, "REQUIRE_HMAC", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)

    async def insert_like_postgres(db, *, events, created_by):
        if any(e["payload"].get("extra") == REFUSED_MARK for e in events):
            raise DataError("INSERT ...", {}, UntranslatableCharacter())
        return {e["evento_id"] for e in events}

    monkeypatch.setattr(service._repo, "insert_new", AsyncMock(side_effect=insert_like_postgres))
    monkeypatch.setattr(service._repo, "find_payloads", AsyncMock(return_value={}))

    session = AsyncMock()
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock()
    savepoint.__aexit__ = AsyncMock(return_value=False)  # re-raise, like SQLAlchemy
    session.begin_nested = MagicMock(return_value=savepoint)

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


def send(client, events):
    return client.post(PATH, json={"eventos": events}, headers={"X-API-Key": API_KEY})


def test_refused_event_is_rejected_and_the_rest_stored(client, db, caplog):
    events = [make_event(), refused(), make_event()]
    with caplog.at_level(logging.WARNING, logger="app.telemetria"):
        response = send(client, events)

    assert response.status_code == 200
    assert response.json() == {
        "aceitos": 2,
        "duplicados": 0,
        "rejeitados": [{
            "evento_id": events[1]["evento_id"],
            "campo": "eventos[1]",
            "mensagem": messages.UNSTORABLE_EVENT,
        }],
    }
    # Bulk attempt rolled back once, then one savepoint per event and a single commit.
    db.rollback.assert_awaited_once()
    assert db.begin_nested.call_count == len(events)
    db.commit.assert_awaited_once()
    assert "telemetria_lote_reprocessado" in caplog.text
    assert '"erro":"UntranslatableCharacter"' in caplog.text
    assert REFUSED_MARK not in caplog.text  # values are never logged


def test_counts_add_up_with_refused_invalid_and_duplicate_events(client):
    repeated = make_event()
    events = [repeated, dict(repeated), refused(), {"evento": "alerta_aberto"}, make_event()]
    body = send(client, events).json()
    assert (body["aceitos"], body["duplicados"], len(body["rejeitados"])) == (2, 1, 2)


def test_every_event_refused_still_returns_200(client, db):
    response = send(client, [refused(), refused()])
    assert response.status_code == 200
    body = response.json()
    assert body["aceitos"] == 0
    assert [r["campo"] for r in body["rejeitados"]] == ["eventos[0]", "eventos[1]"]
    db.commit.assert_awaited_once()


def test_batch_without_refused_values_uses_single_insert(client, db):
    assert send(client, [make_event(), make_event()]).json()["aceitos"] == 2
    db.begin_nested.assert_not_called()
    db.rollback.assert_not_awaited()


def test_other_database_errors_still_return_500(client, db):
    service._repo.insert_new.side_effect = OperationalError("INSERT ...", {}, Exception("connection lost"))
    response = send(client, [make_event()])
    assert response.status_code == 500
    assert response.json() == {"detail": messages.INTERNAL_ERROR}
    db.commit.assert_not_awaited()
