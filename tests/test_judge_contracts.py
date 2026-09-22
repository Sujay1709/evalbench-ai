import json

import pytest
import yaml
from jsonschema import Draft202012Validator, validate
from pydantic import ValidationError

from evalbench.judges import (
    JudgeOutputError,
    RubricDefinition,
    judge_response_format,
    load_rubric,
    parse_judge_output,
)
from tests.conftest import PROJECT_ROOT

RUBRIC_PATH = PROJECT_ROOT / "rubrics/grounded_qa/v1.yaml"
SOURCES = {
    "context": "Normandy is a region in France.",
    "reference": "France",
    "response": "The answer is France.",
}


def valid_output():
    return {
        "assessments": [
            {
                "criterion_id": "answer_quality",
                "score": 2,
                "evidence_source": "reference",
                "evidence_quote": "France",
                "reason": "The answer matches the reference.",
            },
            {
                "criterion_id": "evidence_alignment",
                "score": 1,
                "evidence_source": "context",
                "evidence_quote": "region in France",
                "reason": "The context supports the location, but the answer adds wording.",
            },
        ]
    }


def test_rubric_has_stable_content_hash_independent_of_yaml_key_order(tmp_path):
    first = load_rubric(RUBRIC_PATH)
    original = yaml.safe_load(RUBRIC_PATH.read_text())
    reordered_path = tmp_path / "reordered.yaml"
    reordered_path.write_text(yaml.safe_dump(original, sort_keys=True))

    assert first.content_hash == load_rubric(reordered_path).content_hash
    assert len(first.content_hash) == 64
    assert (
        first.content_hash
        != RubricDefinition.model_validate({**original, "version": "v2"}).content_hash
    )
    original["criteria"][0]["anchors"][0]["description"] += " More detail."
    assert first.content_hash != RubricDefinition.model_validate(original).content_hash


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data.update(version="latest"), "version"),
        (
            lambda data: data["criteria"].append(data["criteria"][0]),
            "criterion IDs must be unique",
        ),
        (
            lambda data: data["criteria"][0]["anchors"].pop(),
            "exactly one anchor each",
        ),
        (
            lambda data: data["criteria"][0]["anchors"][0].update(score=True),
            "score",
        ),
        (
            lambda data: data["criteria"][0].update(description="  "),
            "must not be blank",
        ),
    ],
)
def test_rubric_rejects_invalid_version_criteria_and_anchors(change, message):
    data = yaml.safe_load(RUBRIC_PATH.read_text())
    change(data)
    with pytest.raises(ValidationError, match=message):
        RubricDefinition.model_validate(data)


def test_strict_response_schema_and_parsed_verdict():
    rubric = load_rubric(RUBRIC_PATH)
    output_format = judge_response_format(rubric)
    schema = output_format["schema"]
    Draft202012Validator.check_schema(schema)
    validate(valid_output(), schema)

    assert output_format["type"] == "json_schema"
    assert output_format["name"] == "evalbench_grounded_qa_v1"
    assert output_format["strict"] is True
    assert schema["required"] == ["assessments"]
    assert schema["additionalProperties"] is False
    item_schema = schema["properties"]["assessments"]["items"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == set(item_schema["properties"])
    assert item_schema["properties"]["criterion_id"]["enum"] == [
        "answer_quality",
        "evidence_alignment",
    ]

    verdict = parse_judge_output(
        json.dumps(valid_output()),
        rubric=rubric,
        example_id="squad-example-1",
        sources=SOURCES,
    )
    assert verdict.rubric_id == "grounded_qa"
    assert verdict.rubric_version == "v1"
    assert verdict.rubric_hash == rubric.content_hash
    assert verdict.example_id == "squad-example-1"
    assert verdict.normalized_score == 0.75


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda data: data["assessments"].pop(), "exactly once"),
        (
            lambda data: data["assessments"].append(data["assessments"][0]),
            "exactly once",
        ),
        (
            lambda data: data["assessments"][0].update(criterion_id="invented"),
            "exactly once",
        ),
        (lambda data: data["assessments"][0].update(score=True), "score"),
        (lambda data: data["assessments"][0].update(score=3), "score"),
        (
            lambda data: data["assessments"][0].update(unrequested="extra"),
            "unrequested",
        ),
        (
            lambda data: data["assessments"][0].update(evidence_quote="Germany"),
            "absent from the supplied reference",
        ),
        (
            lambda data: data["assessments"][0].update(
                evidence_source="none", evidence_quote="France"
            ),
            "cannot quote",
        ),
        (
            lambda data: data["assessments"][0].update(evidence_source="none", evidence_quote=""),
            "needs cited text",
        ),
        (
            lambda data: data["assessments"][0].update(reason=" "),
            "nonblank reason",
        ),
    ],
)
def test_parser_rejects_invalid_or_fabricated_assessments(change, message):
    data = valid_output()
    change(data)
    with pytest.raises(JudgeOutputError, match=message):
        parse_judge_output(
            json.dumps(data),
            rubric=load_rubric(RUBRIC_PATH),
            example_id="squad-example-1",
            sources=SOURCES,
        )


def test_parser_rejects_malformed_json_and_missing_source():
    rubric = load_rubric(RUBRIC_PATH)
    with pytest.raises(JudgeOutputError, match="Invalid judge JSON"):
        parse_judge_output("not JSON", rubric=rubric, example_id="case-1", sources=SOURCES)
    with pytest.raises(JudgeOutputError, match="supplied reference"):
        parse_judge_output(
            json.dumps(valid_output()),
            rubric=rubric,
            example_id="case-1",
            sources={"context": SOURCES["context"]},
        )


def test_parser_allows_no_quote_only_with_none_source():
    data = valid_output()
    data["assessments"][0].update(score=0, evidence_source="none", evidence_quote="")
    verdict = parse_judge_output(
        json.dumps(data),
        rubric=load_rubric(RUBRIC_PATH),
        example_id="case-1",
        sources=SOURCES,
    )
    assert verdict.assessments[0].evidence_source == "none"
