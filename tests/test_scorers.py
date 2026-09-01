import pytest

from evalbench.datasets import EvaluationExample, ScorerSpec
from evalbench.runners.scoring import DeterministicScoringError, score_example_output
from evalbench.scorers import score_response


def test_exact_match_normalizes_case_and_whitespace():
    spec = ScorerSpec(type="exact_match", expected="Battery Electric Vehicle")

    result = score_response("  battery   electric vehicle  ", spec)

    assert result.passed is True
    assert result.score == 1.0


def test_json_schema_reports_invalid_output():
    spec = ScorerSpec.model_validate(
        {
            "type": "json_schema",
            "schema": {
                "type": "object",
                "required": ["winner"],
                "properties": {"winner": {"type": "string"}},
            },
        }
    )

    result = score_response('{"missing": "winner"}', spec)

    assert result.passed is False
    assert result.score == 0.0
    assert "error" in result.details


def test_token_f1_uses_best_alias_and_normalizes_text():
    spec = ScorerSpec(
        type="token_f1",
        accepted_answers=["Turing machines", "deterministic Turing machines"],
    )

    result = score_response("The deterministic Turing machines.", spec)

    assert result.passed is True
    assert result.score == 1.0
    assert result.details["best_expected"] == "deterministic Turing machines"


def test_token_f1_assigns_partial_credit_with_a_threshold():
    spec = ScorerSpec(
        type="token_f1",
        accepted_answers=["Umina Beach, New South Wales"],
        threshold=0.5,
    )

    result = score_response("Umina Beach", spec)

    assert result.passed is True
    assert result.score == pytest.approx(4 / 7)
    assert result.details["precision"] == 1.0
    assert result.details["recall"] == 0.4


def test_token_f1_fails_when_answers_do_not_overlap():
    spec = ScorerSpec(type="token_f1", accepted_answers=["France"], threshold=0.5)

    result = score_response("Norway", spec)

    assert result.passed is False
    assert result.score == 0.0


def test_answerability_recognizes_normalized_abstention():
    spec = ScorerSpec(type="answerability", expected_answerable=False)

    result = score_response("Insufficient evidence.", spec)

    assert result.passed is True
    assert result.details["predicted_answerable"] is False


def test_answerability_recognizes_a_substantive_answer():
    spec = ScorerSpec(type="answerability", expected_answerable=True)

    result = score_response("France", spec)

    assert result.passed is True
    assert result.details["predicted_answerable"] is True


def test_token_f1_requires_at_least_one_accepted_answer():
    with pytest.raises(ValueError, match="accepted_answers"):
        ScorerSpec(type="token_f1")


def test_example_scoring_rejects_an_invalid_json_schema_configuration():
    example = EvaluationExample(
        id="invalid-schema",
        input={"question": "Return JSON"},
        mock_response='{"answer": "value"}',
        scorers=[ScorerSpec(type="json_schema", schema={"type": "not-a-json-type"})],
    )

    with pytest.raises(DeterministicScoringError, match="invalid JSON Schema"):
        score_example_output(example.mock_response, example)
