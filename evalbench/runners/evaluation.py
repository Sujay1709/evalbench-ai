import hashlib
import json
import uuid
from datetime import UTC, datetime

from evalbench.datasets import EvaluationExample, LoadedDataset
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

    def run(self, dataset: LoadedDataset, prompt: PromptDefinition) -> EvaluationRun:
        run = EvaluationRun(
            id=str(uuid.uuid4()),
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            dataset_hash=dataset.content_hash,
            prompt_id=prompt.id,
            prompt_version=prompt.version,
            provider=self.provider.name,
            status="running",
            total_examples=len(dataset.examples),
        )
        db.session.add(run)
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
