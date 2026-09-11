from types import SimpleNamespace
from uuid import uuid4

import inngest
import pytest

from evalbench import create_app
from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult, ResponseCache
from evalbench.prompts import load_prompt
from evalbench.providers import (
    MockProvider,
    ProviderResponse,
    ProviderResponseError,
    ProviderTransientError,
)
from evalbench.runners import EvaluationRunner
from evalbench.workflows.failures import (
    FAILURE_EVENT_NAME,
    FailureCategory,
    finalize_evaluation_failure,
    non_retriable_failure,
)
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


class SkippingScoreStep(DirectStep):
    def __init__(self) -> None:
        super().__init__()
        self.skipped = False

    def run(self, step_id, handler):
        if not self.skipped and step_id.startswith("score-response-"):
            self.calls.append(step_id)
            self.skipped = True
            return {"status": "simulated-missing-score"}
        return super().run(step_id, handler)


class CompletionInterruptingStep:
    """Retain prior checkpoints while losing the completion result once."""

    def __init__(self, *, after_handler: bool) -> None:
        self.results: dict[str, object] = {}
        self.interrupted = False
        self.after_handler = after_handler

    def run(self, step_id, handler):
        if step_id in self.results:
            return self.results[step_id]
        if step_id == "aggregate-and-complete-run" and not self.interrupted:
            self.interrupted = True
            if self.after_handler:
                handler()
            raise RuntimeError("simulated completion interruption")
        result = handler()
        self.results[step_id] = result
        return result


def workflow_context(run_id, correlation_id):
    return SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": str(run_id), "correlation_id": str(correlation_id)}
        ),
        step=DirectStep(),
    )


def failure_context(
    run_id,
    correlation_id,
    *,
    error_name="ProviderTransientError",
    error_message="temporary provider outage",
    original_event_name="eval/run.requested",
):
    return SimpleNamespace(
        event=SimpleNamespace(
            name=FAILURE_EVENT_NAME,
            data={
                "error": {
                    "name": error_name,
                    "message": error_message,
                    "stack": "sensitive stack trace",
                },
                "event": {
                    "name": original_event_name,
                    "data": {
                        "run_id": str(run_id),
                        "correlation_id": str(correlation_id),
                    },
                },
                "function_id": "evalbench-eval-run",
                "run_id": "inngest-failed-run-id",
            },
        )
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
    assert callable(client.options["on_failure"])


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
        "status": "completed",
        "run_id": run_id,
        "generated_examples": 3,
        "scored_examples": 3,
        "passed_examples": 3,
        "mean_score": 1.0,
    }
    assert context.step.calls[0] == "validate-persisted-run"
    assert context.step.calls[-1] == "aggregate-and-complete-run"
    assert len(context.step.calls) == 8
    assert len(set(context.step.calls)) == 8
    assert sum(step.startswith("generate-response-") for step in context.step.calls) == 3
    assert sum(step.startswith("score-response-") for step in context.step.calls) == 3
    assert provider.calls == 3
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "completed"
        assert stored_run.passed_examples == 3
        assert stored_run.mean_score == 1.0
        assert stored_run.completed_at is not None
        assert db.session.query(ResponseCache).count() == 3
        stored_results = db.session.execute(
            db.select(ExampleResult).where(ExampleResult.run_id == run_id)
        ).scalars().all()
        assert len(stored_results) == 3
        assert all(result.passed for result in stored_results)
        assert all(result.score == 1.0 for result in stored_results)
        assert all(result.scorer_details for result in stored_results)
        assert all(result.usage_json["estimated_cost_usd"] == 0 for result in stored_results)

    replay = execute_evaluation_run(
        workflow_context(run_id, correlation_id),
        app,
        provider_factory=lambda: provider,
    )

    assert replay == {
        "status": "already_completed",
        "run_id": run_id,
        "generated_examples": 0,
        "scored_examples": 0,
        "passed_examples": 3,
        "mean_score": 1.0,
    }
    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ExampleResult).count() == 3


def test_recovery_acceptance_resumes_without_duplicate_calls_or_writes(app):
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
    with app.app_context():
        interrupted_run = db.session.get(EvaluationRun, run_id)
        assert interrupted_run.status == "running"
        assert interrupted_run.correlation_id == correlation_id
        assert db.session.query(ResponseCache).count() == 1
        assert db.session.query(ExampleResult).count() == 0

    result = execute_evaluation_run(context, app, provider_factory=lambda: provider)

    assert result["status"] == "completed"
    assert provider.calls == 3
    with app.app_context():
        completed_run = db.session.get(EvaluationRun, run_id)
        assert completed_run.status == "completed"
        assert completed_run.correlation_id == correlation_id
        assert completed_run.completed_at is not None
        assert db.session.query(ResponseCache).count() == 3
        stored_results = db.session.execute(
            db.select(ExampleResult)
            .where(ExampleResult.run_id == run_id)
            .order_by(ExampleResult.example_id)
        ).scalars().all()
        assert [result.example_id for result in stored_results] == [
            "auto-001",
            "auto-002",
            "auto-003",
        ]


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

    assert result["status"] == "completed"
    assert provider.calls == 3
    with app.app_context():
        assert db.session.query(ExampleResult).count() == 3


@pytest.mark.parametrize("after_handler", [False, True])
def test_workflow_resumes_around_atomic_completion(app, after_handler):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    step = CompletionInterruptingStep(after_handler=after_handler)
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": run_id, "correlation_id": correlation_id}
        ),
        step=step,
    )

    with pytest.raises(RuntimeError, match="simulated completion interruption"):
        execute_evaluation_run(context, app, provider_factory=lambda: provider)

    with app.app_context():
        interrupted_run = db.session.get(EvaluationRun, run_id)
        expected_status = "completed" if after_handler else "running"
        assert interrupted_run.status == expected_status
        assert db.session.query(ExampleResult).count() == 3

    result = execute_evaluation_run(context, app, provider_factory=lambda: provider)

    expected_result_status = "already_completed" if after_handler else "completed"
    assert result["status"] == expected_result_status
    assert result["passed_examples"] == 3
    assert result["mean_score"] == 1.0
    assert provider.calls == 3
    with app.app_context():
        completed_run = db.session.get(EvaluationRun, run_id)
        assert completed_run.status == "completed"
        assert completed_run.passed_examples == 3
        assert completed_run.mean_score == 1.0
        assert completed_run.completed_at is not None


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
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "running"
        assert stored_run.error_category is None
        assert stored_run.error_message is None
        assert stored_run.completed_at is None


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


def test_workflow_aggregates_a_failed_example_into_final_metrics(app):
    class OneFailureProvider(MockProvider):
        def generate(self, prompt, example):
            response = super().generate(prompt, example)
            if example.id == "auto-002":
                return ProviderResponse(
                    text="incorrect vehicle category",
                    latency_ms=response.latency_ms,
                    metadata=response.metadata,
                )
            return response

    provider = OneFailureProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)

    result = execute_evaluation_run(
        workflow_context(run_id, correlation_id),
        app,
        provider_factory=lambda: provider,
    )

    assert result["status"] == "completed"
    assert result["passed_examples"] == 2
    assert result["mean_score"] == pytest.approx(2 / 3)
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.passed_examples == 2
        assert stored_run.mean_score == pytest.approx(2 / 3)


def test_workflow_refuses_completion_when_an_expected_result_is_missing(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    context = SimpleNamespace(
        event=SimpleNamespace(
            data={"run_id": run_id, "correlation_id": correlation_id}
        ),
        step=SkippingScoreStep(),
    )

    with pytest.raises(inngest.NonRetriableError, match="missing results"):
        execute_evaluation_run(context, app, provider_factory=lambda: provider)

    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "running"
        assert stored_run.passed_examples == 0
        assert stored_run.mean_score == 0.0
        assert stored_run.completed_at is None
        assert db.session.query(ExampleResult).count() == 2


def test_workflow_refuses_completion_with_an_unexpected_result(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    with app.app_context():
        db.session.add(
            ExampleResult(
                run_id=run_id,
                example_id="unexpected-example",
                input_json={"question": "not in the dataset"},
                output_text="unexpected",
                passed=False,
                score=0.0,
                scorer_details=[{"scorer": "fixture"}],
                cache_hit=True,
                latency_ms=0.0,
            )
        )
        db.session.commit()

    with pytest.raises(inngest.NonRetriableError, match="unexpected results"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )

    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "running"
        assert stored_run.completed_at is None


def test_workflow_rejects_conflicting_metrics_on_completed_run(app):
    class CountingProvider(MockProvider):
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    execute_evaluation_run(
        workflow_context(run_id, correlation_id),
        app,
        provider_factory=lambda: provider,
    )
    with app.app_context():
        run = db.session.get(EvaluationRun, run_id)
        run.mean_score = 0.25
        db.session.commit()

    with pytest.raises(inngest.NonRetriableError, match="conflicting aggregate metrics"):
        execute_evaluation_run(
            workflow_context(run_id, correlation_id),
            app,
            provider_factory=lambda: provider,
        )

    assert provider.calls == 3


def test_failure_handler_finalizes_exhausted_provider_retries_without_secrets(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    secret_message = "temporary outage with key sk-test-secret and full prompt"

    result = finalize_evaluation_failure(
        failure_context(
            run_id,
            correlation_id,
            error_message=secret_message,
        ),
        app,
    )

    assert result == {
        "status": "failed",
        "run_id": run_id,
        "correlation_id": correlation_id,
        "error_category": "provider_retries_exhausted",
    }
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "failed"
        assert stored_run.error_category == "provider_retries_exhausted"
        assert stored_run.error_message == (
            "The provider remained unavailable after all retry attempts."
        )
        assert "sk-test-secret" not in stored_run.error_message
        assert "prompt" not in stored_run.error_message
        assert stored_run.completed_at is not None


def test_failure_handler_preserves_tagged_category_and_is_idempotent(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    tagged_error = non_retriable_failure(
        FailureCategory.CONFIGURATION,
        "OPENAI_API_KEY=sk-sensitive-value",
    )
    context = failure_context(
        run_id,
        correlation_id,
        error_name="NonRetriableError",
        error_message=str(tagged_error),
    )

    first_result = finalize_evaluation_failure(context, app)
    with app.app_context():
        first_completed_at = db.session.get(EvaluationRun, run_id).completed_at
    replay_result = finalize_evaluation_failure(context, app)

    assert first_result["error_category"] == "configuration"
    assert replay_result["status"] == "already_failed"
    assert replay_result["error_category"] == "configuration"
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.completed_at == first_completed_at
        assert stored_run.error_message == (
            "The evaluation configuration is invalid or unavailable."
        )
        assert "sk-sensitive-value" not in stored_run.error_message


def test_failure_handler_preserves_completed_run(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    execute_evaluation_run(
        workflow_context(run_id, correlation_id),
        app,
        provider_factory=lambda: provider,
    )
    with app.app_context():
        completed_at = db.session.get(EvaluationRun, run_id).completed_at

    result = finalize_evaluation_failure(
        failure_context(run_id, correlation_id),
        app,
    )

    assert result["status"] == "completed_preserved"
    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "completed"
        assert stored_run.completed_at == completed_at
        assert stored_run.error_category is None
        assert stored_run.error_message is None


def test_failure_handler_preserves_partial_example_evidence(app):
    provider = MockProvider()
    run_id, correlation_id = prepare_automotive_run(app, provider)
    with app.app_context():
        db.session.add(
            ExampleResult(
                run_id=run_id,
                example_id="auto-001",
                input_json={"question": "partial result"},
                output_text="internal combustion engine",
                passed=True,
                score=1.0,
                scorer_details=[{"scorer": "exact_match"}],
                cache_hit=False,
                latency_ms=1.0,
            )
        )
        db.session.commit()

    finalize_evaluation_failure(
        failure_context(run_id, correlation_id),
        app,
    )

    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "failed"
        assert len(stored_run.results) == 1
        assert stored_run.results[0].example_id == "auto-001"


def test_failure_handler_rejects_malformed_event_without_mutating_run(app):
    provider = MockProvider()
    run_id, _ = prepare_automotive_run(app, provider)
    context = SimpleNamespace(
        event=SimpleNamespace(name=FAILURE_EVENT_NAME, data={"unexpected": "payload"})
    )

    with pytest.raises(inngest.NonRetriableError, match="invalid evaluation metadata"):
        finalize_evaluation_failure(context, app)

    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "queued"
        assert stored_run.error_category is None


def test_failure_handler_rejects_correlation_mismatch_without_mutation(app):
    provider = MockProvider()
    run_id, _ = prepare_automotive_run(app, provider)

    with pytest.raises(inngest.NonRetriableError, match="different correlation ID"):
        finalize_evaluation_failure(
            failure_context(run_id, uuid4()),
            app,
        )

    with app.app_context():
        stored_run = db.session.get(EvaluationRun, run_id)
        assert stored_run.status == "queued"
        assert stored_run.completed_at is None
