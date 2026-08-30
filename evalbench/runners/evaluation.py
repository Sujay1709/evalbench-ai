import hashlib
import json
import uuid
from datetime import UTC, datetime

from evalbench.datasets import DatasetSplitError, EvaluationExample, LoadedDataset
from evalbench.extensions import db
from evalbench.models import EvaluationRun, ExampleResult, ResponseCache
from evalbench.prompts import PromptDefinition
from evalbench.providers import Provider
from evalbench.scorers import score_response


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _cache_key(
    provider_name: str,
    prompt: PromptDefinition,
    dataset_hash: str,
    example: EvaluationExample,
) -> str:
    payload = {
        "provider": provider_name,
        "prompt_hash": prompt.content_hash,
        "dataset_hash": dataset_hash,
        "example": example.model_dump(by_alias=True, exclude_none=True, mode="json"),
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


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
                rendered_prompt = prompt.render(example.input)
                cache_key = _cache_key(
                    self.provider.name, prompt, dataset.content_hash, example
                )
                cached_response = db.session.get(ResponseCache, cache_key)

                if cached_response is None:
                    provider_response = self.provider.generate(rendered_prompt, example)
                    output_text = provider_response.text
                    latency_ms = provider_response.latency_ms
                    cache_hit = False
                    db.session.add(
                        ResponseCache(
                            cache_key=cache_key,
                            provider=self.provider.name,
                            output_text=output_text,
                            response_metadata=provider_response.metadata,
                        )
                    )
                else:
                    output_text = cached_response.output_text
                    latency_ms = 0.0
                    cache_hit = True

                scores = [score_response(output_text, spec) for spec in example.scorers]
                example_score = sum(score.score for score in scores) / len(scores)
                passed = all(score.passed for score in scores)

                db.session.add(
                    ExampleResult(
                        run_id=run.id,
                        example_id=example.id,
                        input_json=example.input,
                        output_text=output_text,
                        passed=passed,
                        score=example_score,
                        scorer_details=[score.as_dict() for score in scores],
                        cache_hit=cache_hit,
                        latency_ms=latency_ms,
                    )
                )

            db.session.flush()
            stored_results = list(run.results)
            run.passed_examples = sum(result.passed for result in stored_results)
            run.mean_score = sum(result.score for result in stored_results) / len(stored_results)
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
