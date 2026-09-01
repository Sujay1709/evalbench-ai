import hashlib
import json
from dataclasses import dataclass

from evalbench.datasets import EvaluationExample
from evalbench.extensions import db
from evalbench.models import ResponseCache
from evalbench.prompts import PromptDefinition
from evalbench.providers import Provider


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def response_cache_key(
    provider_name: str,
    prompt: PromptDefinition,
    dataset_hash: str,
    example: EvaluationExample,
) -> str:
    """Build the stable identity shared by synchronous and durable generation."""

    payload = {
        "provider": provider_name,
        "prompt_hash": prompt.content_hash,
        "dataset_hash": dataset_hash,
        "example": example.model_dump(by_alias=True, exclude_none=True, mode="json"),
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


@dataclass(frozen=True)
class GeneratedResponse:
    cache_key: str
    output_text: str
    latency_ms: float
    cache_hit: bool


def generate_or_load_response(
    provider: Provider,
    prompt: PromptDefinition,
    dataset_hash: str,
    example: EvaluationExample,
    *,
    commit_cache: bool = False,
) -> GeneratedResponse:
    """Generate one response or reuse its content-addressed cache entry."""

    cache_key = response_cache_key(provider.name, prompt, dataset_hash, example)
    cached_response = db.session.get(ResponseCache, cache_key)

    if cached_response is not None:
        return GeneratedResponse(
            cache_key=cache_key,
            output_text=cached_response.output_text,
            latency_ms=0.0,
            cache_hit=True,
        )

    rendered_prompt = prompt.render(example.input)
    provider_response = provider.generate(rendered_prompt, example)
    db.session.add(
        ResponseCache(
            cache_key=cache_key,
            provider=provider.name,
            output_text=provider_response.text,
            response_metadata=provider_response.metadata,
        )
    )
    if commit_cache:
        db.session.commit()

    return GeneratedResponse(
        cache_key=cache_key,
        output_text=provider_response.text,
        latency_ms=provider_response.latency_ms,
        cache_hit=False,
    )
