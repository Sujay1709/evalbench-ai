from types import SimpleNamespace
from uuid import uuid4

import inngest
import pytest

from evalbench import create_app
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.workflows.functions import (
    create_workflow_functions,
    validate_evaluation_run_request,
    validate_event_identifiers,
)


class DirectStep:
    """Execute a step immediately while recording its stable checkpoint ID."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, step_id, handler):
        self.calls.append(step_id)
        return handler()


def workflow_context(run_id, correlation_id):
    return SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": str(run_id), "correlation_id": str(correlation_id)}
        ),
        step=DirectStep(),
    )


def add_run(app, *, run_id, correlation_id, status="queued"):
    with app.app_context():
        db.session.add(
            EvaluationRun(
                id=str(run_id),
                correlation_id=str(correlation_id),
                dataset_name="automotive_qa",
                dataset_version="v1",
                dataset_hash="a" * 64,
                dataset_split="development",
                prompt_id="automotive-qa",
                prompt_version="v1",
                provider="mock",
                status=status,
                total_examples=3,
            )
        )
        db.session.commit()


def test_development_app_serves_registered_inngest_function(app, client):
    response = client.get("/api/inngest")

    assert response.status_code == 200
    assert response.headers["x-inngest-sdk-handled"] == "true"
    assert response.get_json()["function_count"] == 1
    assert response.get_json()["mode"] == "dev"
    assert app.extensions["inngest"].app_id == "evalbench"
    assert len(app.extensions["inngest_functions"]) == 1


def test_workflow_registration_uses_run_id_idempotency_and_bounded_retries(app):
    class CapturingClient:
        options = None

        def create_function(self, **options):
            self.options = options

            def register(function):
                return function

            return register

    client = CapturingClient()

    functions = create_workflow_functions(client, app)

    assert len(functions) == 1
    assert client.options["idempotency"] == "event.data.run_id"
    assert client.options["retries"] == 2


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


def test_event_identifier_validation_returns_traceable_identifiers():
    run_id = uuid4()
    correlation_id = uuid4()
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": str(run_id), "correlation_id": str(correlation_id)}
        )
    )

    result = validate_event_identifiers(context)

    assert result == {
        "status": "validated",
        "run_id": str(run_id),
        "correlation_id": str(correlation_id),
    }


def test_event_identifier_validation_does_not_retry_invalid_events():
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": "invalid", "correlation_id": str(uuid4())}
        )
    )

    with pytest.raises(inngest.NonRetriableError, match="invalid identifiers"):
        validate_event_identifiers(context)


def test_workflow_validation_is_a_persisted_idempotent_step(app):
    run_id = uuid4()
    correlation_id = uuid4()
    add_run(app, run_id=run_id, correlation_id=correlation_id)
    context = workflow_context(run_id, correlation_id)

    first_result = validate_evaluation_run_request(context, app)
    replay_result = validate_evaluation_run_request(context, app)

    assert first_result == replay_result == {
        "status": "ready",
        "run_id": str(run_id),
        "correlation_id": str(correlation_id),
    }
    assert context.step.calls == ["validate-persisted-run", "validate-persisted-run"]
    with app.app_context():
        stored_runs = db.session.execute(db.select(EvaluationRun)).scalars().all()
        assert len(stored_runs) == 1
        assert stored_runs[0].status == "running"


def test_workflow_validation_rejects_unknown_run_without_retry(app):
    run_id = uuid4()
    context = workflow_context(run_id, uuid4())

    with pytest.raises(inngest.NonRetriableError, match="does not exist"):
        validate_evaluation_run_request(context, app)


def test_workflow_validation_rejects_correlation_mismatch_without_mutation(app):
    run_id = uuid4()
    correlation_id = uuid4()
    add_run(app, run_id=run_id, correlation_id=correlation_id)
    context = workflow_context(run_id, uuid4())

    with pytest.raises(inngest.NonRetriableError, match="different correlation ID"):
        validate_evaluation_run_request(context, app)

    with app.app_context():
        assert db.session.get(EvaluationRun, str(run_id)).status == "queued"


def test_workflow_validation_short_circuits_completed_run(app):
    run_id = uuid4()
    correlation_id = uuid4()
    add_run(app, run_id=run_id, correlation_id=correlation_id, status="completed")

    result = validate_evaluation_run_request(
        workflow_context(run_id, correlation_id),
        app,
    )

    assert result["status"] == "already_completed"
