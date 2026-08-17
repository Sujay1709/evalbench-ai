from datetime import UTC, datetime

from evalbench.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvaluationRun(db.Model):
    __tablename__ = "evaluation_runs"

    id = db.Column(db.String(36), primary_key=True)
    dataset_name = db.Column(db.String(120), nullable=False)
    dataset_version = db.Column(db.String(80), nullable=False)
    dataset_hash = db.Column(db.String(64), nullable=False)
    prompt_id = db.Column(db.String(120), nullable=False)
    prompt_version = db.Column(db.String(80), nullable=False)
    provider = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="running")
    total_examples = db.Column(db.Integer, nullable=False, default=0)
    passed_examples = db.Column(db.Integer, nullable=False, default=0)
    mean_score = db.Column(db.Float, nullable=False, default=0.0)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime(timezone=True))

    results = db.relationship(
        "ExampleResult",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ExampleResult.example_id",
    )

    @property
    def pass_rate(self) -> float:
        if not self.total_examples:
            return 0.0
        return self.passed_examples / self.total_examples


class ExampleResult(db.Model):
    __tablename__ = "example_results"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.String(36), db.ForeignKey("evaluation_runs.id"), nullable=False)
    example_id = db.Column(db.String(120), nullable=False)
    input_json = db.Column(db.JSON, nullable=False)
    output_text = db.Column(db.Text, nullable=False)
    passed = db.Column(db.Boolean, nullable=False)
    score = db.Column(db.Float, nullable=False)
    scorer_details = db.Column(db.JSON, nullable=False)
    cache_hit = db.Column(db.Boolean, nullable=False, default=False)
    latency_ms = db.Column(db.Float, nullable=False, default=0.0)

    run = db.relationship("EvaluationRun", back_populates="results")

    __table_args__ = (
        db.UniqueConstraint("run_id", "example_id", name="uq_run_example"),
    )


class ResponseCache(db.Model):
    __tablename__ = "response_cache"

    cache_key = db.Column(db.String(64), primary_key=True)
    provider = db.Column(db.String(80), nullable=False)
    output_text = db.Column(db.Text, nullable=False)
    response_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
