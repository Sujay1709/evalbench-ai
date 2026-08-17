from evalbench.datasets import ScorerSpec
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
