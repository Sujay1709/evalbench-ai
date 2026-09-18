import uuid
from datetime import UTC, datetime

from evalbench.datasets import DatasetSplitError, LoadedDataset
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult
from evalbench.prompts import PromptDefinition
from evalbench.providers import Provider
from evalbench.runners.aggregation import aggregate_example_scores
from evalbench.runners.generation import generate_or_load_response
from evalbench.runners.scoring import score_example_output


class EvaluationRunner:
    def __init__(self, provider: Provider):
        self.provider = provider

    def prepare_run(
        self,
        dataset: LoadedDataset,
        prompt: PromptDefinition,
        *,
        correlation_id: uuid.UUID | None = None,
    ) -> EvaluationRun:
        """Persist the queued identity that a synchronous or durable run will use."""

        if dataset.selected_split is None:
            raise DatasetSplitError(
                "Dataset split must be selected before evaluation; "
                "choose development or holdout"
            )
        if any(example.split != dataset.selected_split for example in dataset.examples):
            raise DatasetSplitError(
                f"Selected '{dataset.selected_split.value}' dataset contains mixed split labels"
            )

        correlation_value = str(correlation_id or uuid.uuid4())
        existing_run = db.session.execute(
            db.select(EvaluationRun).where(
                EvaluationRun.correlation_id == correlation_value
            )
        ).scalar_one_or_none()
        if existing_run is not None:
            expected_identity = (
                dataset.name,
                dataset.version,
                dataset.content_hash,
                dataset.selected_split.value,
                prompt.id,
                prompt.version,
                self.provider.name,
            )
            stored_identity = (
                existing_run.dataset_name,
                existing_run.dataset_version,
                existing_run.dataset_hash,
                existing_run.dataset_split,
                existing_run.prompt_id,
                existing_run.prompt_version,
                existing_run.provider,
            )
            if stored_identity != expected_identity:
                raise ValueError(
                    "Correlation ID already belongs to a different evaluation request"
                )
            return existing_run

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            correlation_id=correlation_value,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            dataset_hash=dataset.content_hash,
            dataset_split=dataset.selected_split.value,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            provider=self.provider.name,
            status="queued",
            total_examples=len(dataset.examples),
        )
        db.session.add(run)
        db.session.commit()
        return run

    def run(
        self,
        dataset: LoadedDataset,
        prompt: PromptDefinition,
        *,
        correlation_id: uuid.UUID | None = None,
    ) -> EvaluationRun:
        run = self.prepare_run(
            dataset,
            prompt,
            correlation_id=correlation_id,
        )
        if run.status == "completed":
            return run
        if run.status != "queued":
            raise ValueError(
                f"Evaluation run '{run.id}' cannot start from status '{run.status}'"
            )
        run.status = "running"
        db.session.commit()

        try:
            for example in dataset.examples:
                generated = generate_or_load_response(
                    self.provider,
                    prompt,
                    dataset.content_hash,
                    example,
                )

                scored = score_example_output(generated.output_text, example)

                db.session.add(
                    ExampleResult(
                        run_id=run.id,
                        example_id=example.id,
                        input_json=example.input,
                        output_text=generated.output_text,
                        passed=scored.passed,
                        score=scored.score,
                        scorer_details=scored.scorer_details,
                        cache_hit=generated.cache_hit,
                        latency_ms=generated.latency_ms,
                        usage_json=generated.usage,
                    )
                )

            db.session.flush()
            stored_results = list(run.results)
            metrics = aggregate_example_scores(
                (result.passed, result.score) for result in stored_results
            )
            run.passed_examples = metrics.passed_examples
            run.mean_score = metrics.mean_score
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            db.session.commit()
            return run
        except Exception as exc:
            db.session.rollback()
            persisted_run = db.session.get(EvaluationRun, run.id)
            if persisted_run is not None:
                persisted_run.status = "failed"
                persisted_run.error_message = str(exc)
                persisted_run.completed_at = datetime.now(UTC)
                db.session.commit()
            raise
