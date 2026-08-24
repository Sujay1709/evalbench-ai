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
