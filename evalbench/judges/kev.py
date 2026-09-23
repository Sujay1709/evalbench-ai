"""Opt-in local Kev decision model, isolated from authoritative EvalBench scores."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from evalbench.extensions import db
from evalbench.judges.execution import PreparedJudgment
from evalbench.judges.rubrics import RubricDefinition
from evalbench.models import ExampleResult, KevDecisionAttempt

KEV_MODEL = "kev-latest"
MAX_REQUEST_CHARS = 16_000
MAX_RESPONSE_BYTES = 1_000_000
PINNED_RUN = re.compile(r"^jaredpalmer/kev-[A-Za-z0-9.-]+@[0-9a-f]{40}$")


class KevConfigurationError(ValueError):
    """The local service or checkpoint identity is not safe for a reproducible run."""


class KevResponseError(ValueError):
    """A local Kev response does not satisfy EvalBench's decision contract."""


@dataclass(frozen=True)
class PreparedKevDecision:
    result_id: int
    rubric_hash: str
    payload: dict[str, Any]
    request_hash: str


def validate_local_url(base_url: str) -> str:
    """Only an explicit IPv4 loopback endpoint may receive dataset contents."""
    try:
        parts = urlsplit(base_url)
        port = parts.port
    except ValueError as exc:
        raise KevConfigurationError("KEV_BASE_URL needs a valid loopback port") from exc
    if (
        parts.scheme != "http"
        or parts.hostname != "127.0.0.1"
        or port is None
        or port < 1
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise KevConfigurationError(
            "KEV_BASE_URL must be http://127.0.0.1:PORT with no path or credentials"
        )
    return f"http://127.0.0.1:{port}"


def validate_pinned_run(expected_run: str) -> str:
    if not PINNED_RUN.fullmatch(expected_run):
        raise KevConfigurationError(
            "--expected-run must be a Kev Hub ID pinned to a 40-character commit SHA"
        )
    return expected_run


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(canonical) > MAX_REQUEST_CHARS:
        raise KevConfigurationError(
            f"Kev request exceeds {MAX_REQUEST_CHARS} characters; use a shorter example"
        )
    return hashlib.sha256(canonical.encode()).hexdigest()


def prepare_kev_decision(
    prepared: PreparedJudgment, *, rubric: RubricDefinition
) -> PreparedKevDecision:
    """Map existing grounded-QA evidence to Kev's ordered 0/1/2 score questions."""
    if prepared.rubric_hash != rubric.content_hash:
        raise KevConfigurationError("Rubric changed after the result was prepared")
    payload = {
        "model": KEV_MODEL,
        "state": {
            "question": prepared.question,
            "context": prepared.sources["context"],
            "reference_answer": prepared.sources["reference"],
            "reference_answerable": bool(prepared.sources["reference"]),
            "candidate_response": prepared.sources["response"],
        },
        "questions": {
            criterion.id: {
                "type": "score",
                "instructions": criterion.description,
                "criteria": [
                    anchor.description
                    for anchor in sorted(criterion.anchors, key=lambda a: a.score)
                ],
            }
            for criterion in rubric.criteria
        },
    }
    return PreparedKevDecision(
        result_id=prepared.result_id,
        rubric_hash=rubric.content_hash,
        payload=payload,
        request_hash=_request_hash(payload),
    )


def _json_object(response: httpx.Response, name: str) -> dict[str, Any]:
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise KevResponseError(f"Kev {name} response exceeds the size limit")
    try:
        payload = response.json()
    except ValueError as exc:
        raise KevResponseError(f"Kev {name} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise KevResponseError(f"Kev {name} must return a JSON object")
    return payload


def _model_card(payload: dict[str, Any], expected_run: str) -> dict[str, Any]:
    cards = payload.get("models")
    if not isinstance(cards, list):
        raise KevResponseError("Kev /v1/models did not return a models list")
    matched = [card for card in cards if isinstance(card, dict) and card.get("name") == KEV_MODEL]
    if len(matched) != 1:
        raise KevResponseError("Kev /v1/models needs exactly one kev-latest card")
    card = matched[0]
    if card.get("run") != expected_run:
        raise KevConfigurationError("Kev server checkpoint differs from --expected-run")
    temperature = card.get("temperature")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature)
        or temperature <= 0
    ):
        raise KevResponseError("Kev model card needs a positive finite temperature")
    return card


def _ratings(payload: dict[str, Any], rubric: RubricDefinition) -> list[dict[str, Any]]:
    if payload.get("model") != KEV_MODEL:
        raise KevResponseError("Kev response model does not match kev-latest")
    answers = payload.get("answers")
    expected = {criterion.id for criterion in rubric.criteria}
    if not isinstance(answers, dict) or set(answers) != expected:
        raise KevResponseError("Kev answer IDs must match the rubric criteria exactly")
    ratings = []
    for criterion in rubric.criteria:
        answer = answers[criterion.id]
        if not isinstance(answer, dict) or answer.get("type") != "score":
            raise KevResponseError(f"Kev criterion '{criterion.id}' needs a score answer")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != {"0", "1", "2"}:
            raise KevResponseError(f"Kev criterion '{criterion.id}' needs 0/1/2 probabilities")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in probabilities.values()
        ) or abs(sum(probabilities.values()) - 1) > 0.001:
            raise KevResponseError(f"Kev criterion '{criterion.id}' has invalid probabilities")
        score = answer.get("score")
        calculated = probabilities["1"] + 2 * probabilities["2"]
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 2
            or abs(score - calculated) > 0.002
        ):
            raise KevResponseError(f"Kev criterion '{criterion.id}' has an inconsistent score")
        anchors = [
            anchor.description for anchor in sorted(criterion.anchors, key=lambda a: a.score)
        ]
        if answer.get("legend") != dict(zip(("0", "1", "2"), anchors, strict=True)):
            raise KevResponseError(f"Kev criterion '{criterion.id}' has an unexpected legend")
        ratings.append(
            {
                "criterion_id": criterion.id,
                "expected_score": score,
                "modal_score": max(range(3), key=lambda level: probabilities[str(level)]),
                "probabilities": probabilities,
            }
        )
    return ratings


def execute_kev_decision(
    prepared: PreparedKevDecision,
    *,
    rubric: RubricDefinition,
    expected_run: str,
    base_url: str = "http://127.0.0.1:8009",
    api_key: str | None = None,
    timeout_seconds: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> KevDecisionAttempt:
    """Check checkpoint identity, make at most one inference call, save the outcome."""
    validate_pinned_run(expected_run)
    base_url = validate_local_url(base_url)
    if prepared.rubric_hash != rubric.content_hash:
        raise KevConfigurationError("Rubric changed after the Kev request was prepared")
    if prepared.request_hash != _request_hash(prepared.payload):
        raise KevConfigurationError("Kev request changed after it was prepared")
    if db.session.get(ExampleResult, prepared.result_id) is None:
        raise KevConfigurationError("The evaluation result no longer exists")
    if not 0 < timeout_seconds <= 120:
        raise KevConfigurationError("KEV_TIMEOUT_SECONDS must be between 0 and 120")

    attempt = KevDecisionAttempt(
        id=str(uuid4()),
        result_id=prepared.result_id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        expected_run=expected_run,
        request_hash=prepared.request_hash,
        request_json=prepared.payload,
        status="provider_error",
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            metadata_response = client.get("/v1/models")
            metadata_response.raise_for_status()
            model_card = _model_card(_json_object(metadata_response, "model card"), expected_run)
            attempt.model_card_json = model_card
            response = client.post("/v1/systemone", json=prepared.payload)
            response.raise_for_status()
            attempt.request_id = response.headers.get("x-typesafe-request-id", "")[:120] or None
            attempt.response_json = _json_object(response, "decision")
            attempt.ratings_json = _ratings(attempt.response_json, rubric)
            attempt.status = "completed"
    except KevConfigurationError as exc:
        attempt.status = "identity_mismatch"
        attempt.error_message = str(exc)
    except KevResponseError as exc:
        attempt.status = "invalid_output"
        attempt.error_message = str(exc)
    except httpx.HTTPStatusError as exc:
        attempt.error_message = f"Kev HTTP {exc.response.status_code}; check local server/key"
    except httpx.RequestError as exc:
        attempt.error_message = f"Kev connection failed ({type(exc).__name__}); start the server"

    db.session.add(attempt)
    db.session.commit()
    return attempt
