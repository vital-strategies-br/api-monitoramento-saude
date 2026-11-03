import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.repositories.alert_repo import AlertRepository
from app.db.session import get_db
from app.main import app
from app.models.individual_event import IndividualEvent
from app.api.v1.endpoints.relation import service


def make_event(method="modelo_semantica_explicita"):
    return IndividualEvent(
        id=12, individuo_id=7, tipo_evento="violencia",
        metodo_identificacao=method, data_identificacao=date(2026, 10, 1),
        banco_origem_identificacao=None, id_registro_identificacao=None,
        gera_alerta=True,
    )


@pytest.fixture
def setup_request(monkeypatch):
    monkeypatch.setattr(settings, "API_KEYS", "test-api-key")
    monkeypatch.setattr(settings, "REQUIRE_HMAC", False)
    monkeypatch.setattr(settings, "ENFORCE_ORIGIN_CHECK", False)
    db = AsyncMock()
    monkeypatch.setattr(service._relation_repo, "find_individuals", AsyncMock(return_value=[7]))
    monkeypatch.setattr(service._relation_repo, "find_identification_event", AsyncMock(return_value=make_event()))
    monkeypatch.setattr(service._alert_repo, "record_response", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(service._metrics_repo, "increment_daily", AsyncMock())

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield db, TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def request_alert(client):
    return client.post(
        "/api/v1/relacao/violencia",
        json={"identificadores": [
            {"tipo": "cpf", "valor": "123.456.789-01"},
            {"tipo": "cns", "valor": "700000000000000"},
        ]},
        headers={"X-API-Key": "test-api-key"},
    )


@pytest.mark.parametrize("method", [
    "notificacao_sinan", "modelo_semantica_explicita", "modelo_classificacao_provavel",
])
def test_positive_response_is_audited_before_success(setup_request, method):
    db, client = setup_request
    service._relation_repo.find_identification_event.return_value = make_event(method)
    response = request_alert(client)
    assert response.status_code == 200
    assert response.json()["alerta_id"] == str(service._alert_repo.record_response.return_value)
    assert response.json()["metodo_identificacao"] == method
    assert response.json()["data_identificacao"] == "2026-10-01"
    audit = service._alert_repo.record_response.call_args.kwargs
    assert audit["identifier_pairs"] == [("cpf", "12345678901"), ("cns", "700000000000000")]
    assert audit["endpoint"] == "/api/v1/relacao/violencia"
    assert service._metrics_repo.increment_daily.call_args.kwargs["positive"] is True
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize("known_individual", [True, False])
def test_negative_response_has_no_alert(setup_request, known_individual):
    db, client = setup_request
    service._relation_repo.find_individuals.return_value = [7] if known_individual else []
    service._relation_repo.find_identification_event.return_value = None
    response = request_alert(client)
    assert response.status_code == 200
    assert response.json()["relacionado"] is False
    assert response.json()["alerta_id"] is None
    service._alert_repo.record_response.assert_not_awaited()
    assert service._metrics_repo.increment_daily.call_args.kwargs["positive"] is False
    db.commit.assert_awaited_once()


def test_conflicting_identifiers_returns_409_and_records_metric(setup_request):
    db, client = setup_request
    service._relation_repo.find_individuals.return_value = [1, 2]
    response = request_alert(client)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDENTIFICADORES_CONFLITANTES"
    service._relation_repo.find_identification_event.assert_not_awaited()
    service._alert_repo.record_response.assert_not_awaited()
    metric = service._metrics_repo.increment_daily.call_args.kwargs
    assert metric["identification_method"] is None
    assert metric["positive"] is False
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


def test_sinan_response_matches_documented_payload(setup_request):
    _, client = setup_request
    event = make_event("notificacao_sinan")
    event.data_identificacao = date(2026, 10, 28)
    event.banco_origem_identificacao = "Sinan - Violências"
    event.id_registro_identificacao = "1234567890"
    service._relation_repo.find_identification_event.return_value = event
    service._alert_repo.record_response.return_value = UUID(
        "3f6c2a1e-8b4d-4c2f-9a7e-1d2b3c4d5e6f"
    )

    response = request_alert(client)

    assert response.status_code == 200
    assert response.json() == {
        "relacionado": True,
        "alerta_id": "3f6c2a1e-8b4d-4c2f-9a7e-1d2b3c4d5e6f",
        "metodo_identificacao": "notificacao_sinan",
        "data_identificacao": "2026-10-28",
        "banco_origem_identificacao": "Sinan - Violências",
        "id_registro_identificacao": "1234567890",
    }


@pytest.mark.parametrize("failure", ["audit", "metrics", "commit"])
def test_failed_positive_transaction_returns_500(setup_request, failure):
    db, client = setup_request
    target = {
        "audit": service._alert_repo.record_response,
        "metrics": service._metrics_repo.increment_daily,
        "commit": db.commit,
    }[failure]
    target.side_effect = RuntimeError("database unavailable")
    response = request_alert(client)
    assert response.status_code == 500
    db.rollback.assert_awaited_once()
    if failure != "commit":
        db.commit.assert_not_awaited()


def test_repository_records_distinct_identifiers_and_response_snapshot():
    db = AsyncMock()
    alert_id = uuid4()
    # AsyncSession.execute returns a synchronous result object.
    db.execute.return_value = Mock()
    db.execute.return_value.scalar_one.return_value = alert_id
    result = asyncio.run(AlertRepository().record_response(
        db, event=make_event(), endpoint="/api/v1/relacao/violencia",
        identifier_pairs=[("cpf", "123"), ("cpf", "123"), ("cns", "456")],
    ))
    assert result == alert_id
    calls = db.execute.call_args_list
    snapshot = calls[1].args[0].compile().params
    assert snapshot["alerta_id"] == alert_id
    assert snapshot["metodo_identificacao"] == "modelo_semantica_explicita"
    assert snapshot["data_identificacao"] == date(2026, 10, 1)
    identifiers = calls[2].args[1]
    assert len(identifiers) == 2
    assert all(row["resposta_id"] == snapshot["id"] for row in identifiers)
    db.commit.assert_not_awaited()
