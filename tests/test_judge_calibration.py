"""Offline tests for explicit human/judge calibration pairing."""

import pytest

from evalbench.judges.calibration import CalibrationError, pair_selected_attempts
from evalbench.judges.rubrics import load_rubric
from evalbench.models import HumanLabelSet, JudgeAttempt
from tests.conftest import PROJECT_ROOT

RUBRIC_PATH = PROJECT_ROOT / "rubrics" / "grounded_qa" / "v1.yaml"


@pytest.fixture
def rubric():
    return load_rubric(RUBRIC_PATH)


def _selected_pair(rubric, *, result_id=1, judge_id="judge-1", human_id="human-1"):
    judge = JudgeAttempt(
        id=judge_id,
        result_id=result_id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        status="completed",
        assessments_json=[
            {"criterion_id": "answer_quality", "score": 2},
            {"criterion_id": "evidence_alignment", "score": 1},
        ],
    )
    human = HumanLabelSet(
        id=human_id,
        result_id=result_id,
        rubric_id=rubric.id,
        rubric_version=rubric.version,
        rubric_hash=rubric.content_hash,
        ratings_json=[
            {"criterion_id": "answer_quality", "score": 1},
            {"criterion_id": "evidence_alignment", "score": 1},
        ],
    )
    return judge, human


def test_pairs_scores_by_criterion_id_and_sorts_results(rubric):
    first = _selected_pair(rubric)
    second = _selected_pair(rubric, result_id=2, judge_id="judge-2", human_id="human-2")
    second[0].assessments_json.reverse()

    pairs = pair_selected_attempts([second, first], rubric=rubric)

    assert [pair.result_id for pair in pairs] == [1, 2]
    assert pairs[0].rubric_hash == rubric.content_hash
    assert pairs[0].judge_attempt_id == "judge-1"
    assert pairs[0].human_label_id == "human-1"
    assert [
        (item.criterion_id, item.human_score, item.judge_score) for item in pairs[1].criteria
    ] == [
        ("answer_quality", 1, 2),
        ("evidence_alignment", 1, 1),
    ]


def test_requires_at_least_one_explicit_selection(rubric):
    with pytest.raises(CalibrationError, match="Select at least one"):
        pair_selected_attempts([], rubric=rubric)


def test_rejects_different_results_and_incomplete_judge(rubric):
    judge, human = _selected_pair(rubric)
    human.result_id = 2
    with pytest.raises(CalibrationError, match="same result"):
        pair_selected_attempts([(judge, human)], rubric=rubric)

    human.result_id = 1
    judge.status = "failed"
    with pytest.raises(CalibrationError, match="not completed"):
        pair_selected_attempts([(judge, human)], rubric=rubric)


@pytest.mark.parametrize("source", ["judge", "human"])
def test_rejects_rubric_identity_mismatch(rubric, source):
    judge, human = _selected_pair(rubric)
    selected = judge if source == "judge" else human
    selected.rubric_hash = "0" * 64

    with pytest.raises(CalibrationError, match="selected rubric version"):
        pair_selected_attempts([(judge, human)], rubric=rubric)


def test_rejects_duplicate_selection_for_a_result(rubric):
    judge, human = _selected_pair(rubric)
    another_judge, another_human = _selected_pair(rubric, judge_id="judge-2", human_id="human-2")

    with pytest.raises(CalibrationError, match="selected once"):
        pair_selected_attempts([(judge, human), (another_judge, another_human)], rubric=rubric)


@pytest.mark.parametrize("source", ["judge", "human"])
@pytest.mark.parametrize(
    ("invalid_rows", "message"),
    [
        (None, "ratings must be a list"),
        ([None], "rating must be an object"),
        ([{"score": 1}], "needs a criterion_id"),
        (
            [
                {"criterion_id": "answer_quality", "score": 1},
                {"criterion_id": "answer_quality", "score": 2},
            ],
            "repeats criterion",
        ),
        ([{"criterion_id": "answer_quality", "score": 1}], "missing="),
        (
            [
                {"criterion_id": "answer_quality", "score": 1},
                {"criterion_id": "evidence_alignment", "score": 1},
                {"criterion_id": "invented", "score": 1},
            ],
            "extra=",
        ),
    ],
)
def test_rejects_incomplete_or_malformed_criterion_rows(rubric, source, invalid_rows, message):
    judge, human = _selected_pair(rubric)
    if source == "judge":
        judge.assessments_json = invalid_rows
    else:
        human.ratings_json = invalid_rows

    with pytest.raises(CalibrationError, match=message):
        pair_selected_attempts([(judge, human)], rubric=rubric)


@pytest.mark.parametrize("source", ["judge", "human"])
@pytest.mark.parametrize("invalid_score", [-1, 3, True, 1.0, "1"])
def test_rejects_scores_outside_strict_ordinal_scale(rubric, source, invalid_score):
    judge, human = _selected_pair(rubric)
    if source == "judge":
        judge.assessments_json[0]["score"] = invalid_score
    else:
        human.ratings_json[0]["score"] = invalid_score

    with pytest.raises(CalibrationError, match="needs score 0, 1, or 2"):
        pair_selected_attempts([(judge, human)], rubric=rubric)
