from types import SimpleNamespace
from uuid import uuid4

import inngest
import pytest

from evalbench import create_app
from evalbench.workflows.functions import validate_evaluation_run_request


def test_development_app_serves_registered_inngest_function(app, client):
    response = client.get("/api/inngest")

    assert response.status_code == 200
    assert response.headers["x-inngest-sdk-handled"] == "true"
    assert response.get_json()["function_count"] == 1
    assert response.get_json()["mode"] == "dev"
    assert app.extensions["inngest"].app_id == "evalbench"
    assert len(app.extensions["inngest_functions"]) == 1


def test_production_endpoint_rejects_unsigned_invocations(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret")
    monkeypatch.setenv("DEMO_READ_ONLY", "false")
    monkeypatch.setenv("INNGEST_SIGNING_KEY", "signkey-test-evalbench")

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'inngest.db'}",
        }
    )
    client = app.test_client()

    invocation = client.post("/api/inngest", json={})
    synchronization = client.put("/api/inngest", json={})

    assert invocation.status_code == 401
    assert synchronization.status_code == 401


def test_read_only_demo_does_not_expose_inngest_endpoint(tmp_path):
    read_only_app = create_app(
        {
            "TESTING": True,
            "DEMO_READ_ONLY": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'read-only.db'}",
            "SECRET_KEY": "test-secret",
        }
    )

    response = read_only_app.test_client().get("/api/inngest")

    assert response.status_code == 404
    assert "inngest" not in read_only_app.extensions


def test_workflow_validation_returns_traceable_identifiers():
    run_id = uuid4()
    correlation_id = uuid4()
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": str(run_id), "correlation_id": str(correlation_id)}
        )
    )

    result = validate_evaluation_run_request(context)

    assert result == {
        "status": "validated",
        "run_id": str(run_id),
        "correlation_id": str(correlation_id),
    }


def test_workflow_validation_does_not_retry_invalid_events():
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": "invalid", "correlation_id": str(uuid4())}
        )
    )

    with pytest.raises(inngest.NonRetriableError, match="invalid identifiers"):
        validate_evaluation_run_request(context)
