from evalbench.extensions import db
from evalbench.models import EvaluationRun


def test_homepage_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Replace prompt intuition with evidence" in response.data


def test_dashboard_and_run_detail_display_the_dataset_split(app, client):
    with app.app_context():
        run = EvaluationRun(
            id="split-test-run",
            correlation_id="correlation-test-run",
            dataset_name="automotive_qa",
            dataset_version="v1",
            dataset_hash="a" * 64,
            dataset_split="holdout",
            prompt_id="automotive-qa",
            prompt_version="v1",
            provider="mock",
            status="completed",
            total_examples=2,
            passed_examples=2,
            mean_score=1.0,
        )
        db.session.add(run)
        db.session.commit()

    homepage = client.get("/")
    detail = client.get("/runs/split-test-run")

    assert homepage.status_code == 200
    assert b"<th>Split</th>" in homepage.data
    assert b"Holdout" in homepage.data
    assert detail.status_code == 200
    assert b"Dataset split" in detail.data
    assert b"Holdout" in detail.data
    assert b"Correlation ID" in detail.data
    assert b"correlation-" in detail.data


def test_failed_run_detail_displays_accessible_safe_diagnostic(app, client):
    with app.app_context():
        db.session.add(
            EvaluationRun(
                id="failed-test-run",
                correlation_id="failed-correlation-id",
                dataset_name="automotive_qa",
                dataset_version="v1",
                dataset_hash="b" * 64,
                dataset_split="development",
                prompt_id="automotive-qa",
                prompt_version="v1",
                provider="mock",
                status="failed",
                total_examples=3,
                error_category="provider_retries_exhausted",
                error_message="The provider remained unavailable after all retry attempts.",
            )
        )
        db.session.commit()

    detail = client.get("/runs/failed-test-run")

    assert detail.status_code == 200
    assert b'role="alert"' in detail.data
    assert b"Evaluation did not complete" in detail.data
    assert b"Provider Retries Exhausted" in detail.data
    assert b"The provider remained unavailable after all retry attempts." in detail.data
    assert b"failed-correlation-id" in detail.data
