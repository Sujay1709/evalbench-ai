from types import SimpleNamespace
from uuid import uuid4

import inngest
import pytest

from evalbench import create_app
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult, ResponseCache
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider, ProviderResponseError, ProviderTransientError
from evalbench.runners import EvaluationRunner
from evalbench.workflows.functions import (
    create_workflow_functions,
    execute_evaluation_run,
    validate_evaluation_run_request,
    validate_event_identifiers,
)
from tests.conftest import PROJECT_ROOT


class DirectStep:
    """Execute a step immediately while recording its stable checkpoint ID."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, step_id, handler):
        self.calls.append(step_id)
        return handler()


class MemoizedInterruptingStep:
    """Model Inngest replay by retaining completed steps across an interruption."""

    def __init__(self, interrupt_prefix: str = "generate-response-") -> None:
        self.calls: list[str] = []
        self.results: dict[str, object] = {}
        self.interrupted = False
        self.interrupt_prefix = interrupt_prefix

    def run(self, step_id, handler):
        self.calls.append(step_id)
        if step_id in self.results:
            return self.results[step_id]
        completed_target_steps = [
            key for key in self.results if key.startswith(self.interrupt_prefix)
        ]
        if (
            not self.interrupted
            and len(completed_target_steps) == 1
            and step_id.startswith(self.interrupt_prefix)
        ):
            self.interrupted = True
            raise RuntimeError("simulated worker interruption")
        result = handler()
        self.results[step_id] = result
        return result


class TamperingStep(DirectStep):
    def run(self, step_id, handler):
        result = super().run(step_id, handler)
        if step_id.startswith("generate-response-"):
            return {**result, "cache_key": "0" * 64}
        return result


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


def prepare_automotive_run(app, provider):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
    ).select_split(EvaluationSplit.DEVELOPMENT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")
    with app.app_context():
        run = EvaluationRunner(provider).prepare_run(dataset, prompt)
        return run.id, run.correlation_id


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


def test_workflow_generates_and_scores_each_response_in_stable_checkpoints(app):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    context = workflow_context(run_id, correlation_id)

    result = execute_evaluation_run(
        context,
        app,
        provider_factory=lambda: provider,
    )

    assert result == {
        "status": "responses_scored",
        "run_id": run_id,
        "generated_examples": 3,
        "scored_examples": 3,
    }
    assert context.step.calls[0] == "validate-persisted-run"
    assert len(context.step.calls) == 7
    assert len(set(context.step.calls)) == 7
    assert sum(step.startswith("generate-response-") for step in context.step.calls) == 3
    assert sum(step.startswith("score-response-") for step in context.step.calls) == 3
    assert provider.calls == 3
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "running"
        assert stored_run.passed_examples == 0
        assert stored_run.mean_score == 0.0
        assert db.session.query(ResponseCache).count() == 3
        stored_results = db.session.execute(
            db.select(ExampleResult).where(ExampleResult.run_id == run_id)
        ).scalars().all()
        assert len(stored_results) == 3
        assert all(result.passed for result in stored_results)
        assert all(result.score == 1.0 for result in stored_results)
        assert all(result.scorer_details for result in stored_results)

    replay = execute_evaluation_run(
        workflow_context(run_id, correlation_id),
        app,
        provider_factory=lambda: provider,
    )

    assert replay["status"] == "responses_scored"
    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ExampleResult).count() == 3


def test_workflow_resumes_after_interruption_without_duplicate_provider_calls(app):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    step = MemoizedInterruptingStep()
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": run_id, "correlation_id": correlation_id}
        ),
        step=step,
    )

    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        execute_evaluation_run(context, app, provider_factory=lambda: provider)

    assert step.interrupted is True
    assert provider.calls == 1
    result = execute_evaluation_run(context, app, provider_factory=lambda: provider)

    assert result["status"] == "responses_scored"
    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ResponseCache).count() == 3
        assert db.session.query(ExampleResult).count() == 3


def test_workflow_resumes_scoring_without_duplicate_results(app):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    step = MemoizedInterruptingStep(interrupt_prefix="score-response-")
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": run_id, "correlation_id": correlation_id}
        ),
        step=step,
    )

    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        execute_evaluation_run(context, app, provider_factory=lambda: provider)

    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ResponseCache).count() == 3
        assert db.session.query(ExampleResult).count() == 1

    result = execute_evaluation_run(context, app, provider_factory=lambda: provider)

    assert result["status"] == "responses_scored"
    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ExampleResult).count() == 3


def test_workflow_leaves_transient_provider_failure_retriable(app):
    class TransientProvider(MockProvider):
        def generate(self, prompt, example):
            raise ProviderTransientError("temporary outage")

    provider = TransientProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)

    with pytest.raises(ProviderTransientError, match="temporary outage"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )

    with app.app_context():
        assert db.session.query(ResponseCache).count() == 0


def test_workflow_marks_invalid_provider_response_non_retriable(app):
    class EmptyProvider(MockProvider):
        def generate(self, prompt, example):
            raise ProviderResponseError("empty response")

    provider = EmptyProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)

    with pytest.raises(inngest.NonRetriableError, match="empty response"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )


def test_workflow_rejects_changed_dataset_before_provider_call(app):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        run.dataset_hash = "f" * 64
        db.session.commit()

    with pytest.raises(inngest.NonRetriableError, match="content hash"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )

    assert provider.calls == 0


def test_workflow_rejects_provider_identity_mismatch_before_generation(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        run.provider = "openai:different-model:max128"
        db.session.commit()

    with pytest.raises(inngest.NonRetriableError, match="does not match"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )

    with app.app_context():
        assert db.session.query(ResponseCache).count() == 0


def test_workflow_rejects_generation_checkpoint_for_wrong_cache_key(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": run_id, "correlation_id": correlation_id}
        ),
        step=TamperingStep(),
    )

    with pytest.raises(inngest.NonRetriableError, match="cache key does not match"):
        execute_evaluation_run(context, app, provider_factory=lambda: provider)

    with app.app_context():
        assert db.session.query(ResponseCache).count() == 1
        assert db.session.query(ExampleResult).count() == 0
