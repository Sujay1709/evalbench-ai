import json

import pytest

from evalbench.datasets import (
    BehavioralRelation,
    DatasetValidationError,
    EvaluationExample,
    EvaluationSplit,
    LoadedDataset,
    build_behavioral_examples,
    load_jsonl,
    summarize_behavioral_contracts,
)
from evalbench.datasets.contracts import BehavioralContractError
from evalbench.datasets.perturbations import (
    PERTURBATION_KINDS,
    automotive_perturbations,
    behavioral_fixture_sources,
)
from evalbench.runners.aggregation import aggregate_example_scores
from evalbench.runners.scoring import score_example_output
from tests.conftest import PROJECT_ROOT

BEHAVIORAL_DATASET = PROJECT_ROOT / "datasets" / "automotive_qa" / "behavioral_v1.jsonl"
AUTOMOTIVE_V1 = PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"


def _line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _root(example_id: str = "src", split: str = "development") -> dict:
    return {
        "id": example_id,
        "input": {"question": "What is the value?", "evidence": "The value is 10."},
        "mock_response": "10",
        "scorers": [{"type": "exact_match", "expected": "10"}],
        "split": split,
    }


def _write(tmp_path, *payloads: dict):
    path = tmp_path / "contracts.jsonl"
    path.write_text("".join(f"{_line(payload)}\n" for payload in payloads))
    return path


def _outcomes(examples, overrides: dict[str, str] | None = None) -> dict[str, bool]:
    replacements = overrides or {}
    outcomes = {}
    for example in examples:
        output = replacements.get(example.id, example.mock_response)
        outcomes[example.id] = score_example_output(output, example).passed
    return outcomes


def test_existing_automotive_rows_omit_an_absent_contract():
    dataset = load_jsonl(AUTOMOTIVE_V1)

    assert len(dataset.examples) == 5
    assert all(example.contract is None for example in dataset.examples)
    dumped = dataset.examples[0].model_dump(by_alias=True, exclude_none=True, mode="json")
    assert "contract" not in dumped


def test_behavioral_fixture_matches_the_generator_and_keeps_a_stable_hash():
    loaded = load_jsonl(BEHAVIORAL_DATASET)
    generated = build_behavioral_examples()
    dumped = [
        example.model_dump(by_alias=True, exclude_none=True, mode="json") for example in generated
    ]

    loaded_dump = [
        example.model_dump(by_alias=True, exclude_none=True, mode="json")
        for example in loaded.examples
    ]
    assert loaded_dump == dumped
    assert BEHAVIORAL_DATASET.read_text().splitlines() == [
        _line(payload) for payload in dumped
    ]
    assert load_jsonl(BEHAVIORAL_DATASET).content_hash == loaded.content_hash
    assert len(loaded.content_hash) == 64
    assert len(loaded.examples) == 12
    assert automotive_perturbations(behavioral_fixture_sources()[0]) == automotive_perturbations(
        behavioral_fixture_sources()[0]
    )


def test_each_split_keeps_its_source_with_every_perturbation():
    dataset = load_jsonl(BEHAVIORAL_DATASET)

    for split, source_id in (
        (EvaluationSplit.DEVELOPMENT, "auto-behavior-001"),
        (EvaluationSplit.HOLDOUT, "auto-behavior-002"),
    ):
        selected = dataset.select_split(split)
        ids = [example.id for example in selected.examples]
        assert ids[0] == source_id
        assert ids[1:] == [f"{source_id}-{kind}" for kind in PERTURBATION_KINDS]
        assert selected.content_hash != dataset.content_hash
        assert all(example.split is split for example in selected.examples)


def test_perturbation_order_and_expectations_are_deterministic():
    source = behavioral_fixture_sources()[0]
    derived = automotive_perturbations(source)
    by_kind = {example.id.removeprefix(f"{source.id}-"): example for example in derived}

    assert tuple(by_kind) == PERTURBATION_KINDS
    assert by_kind["casing"].input["question"] == source.input["question"].upper()
    assert by_kind["casing"].scorers[0].expected == "250 miles"
    assert by_kind["harmless-wording"].input["question"].startswith("Please answer this: ")
    assert by_kind["numeric-evidence"].scorers[0].expected == "267 miles"
    assert "267" in by_kind["numeric-evidence"].input["evidence"]
    assert by_kind["missing-evidence"].input["evidence"] == ""
    assert by_kind["missing-evidence"].scorers[0].expected == "Insufficient evidence"
    assert by_kind["contradictory-evidence"].scorers[0].expected == "Insufficient evidence"
    assert all(
        example.contract is not None and example.contract.source_example_id == source.id
        for example in derived
    )
    assert [example.contract.relation for example in derived[:2]] == [
        BehavioralRelation.INVARIANCE,
        BehavioralRelation.INVARIANCE,
    ]
    directional = [example.contract.relation for example in derived[2:]]
    assert directional == [BehavioralRelation.DIRECTIONAL] * 3


def test_mock_answers_pass_contracts_without_replacing_exact_match():
    examples = build_behavioral_examples()
    scored = [score_example_output(example.mock_response, example) for example in examples]
    report = summarize_behavioral_contracts(examples, _outcomes(examples))
    metrics = aggregate_example_scores((item.passed, item.score) for item in scored)

    assert metrics.passed_examples == metrics.total_examples == 12
    assert metrics.mean_score == 1.0
    scorers = {detail["scorer"] for item in scored for detail in item.scorer_details}
    assert scorers == {"exact_match"}
    assert report.minimum_functionality == report.minimum_functionality_passed == 2
    assert report.invariance == 4
    assert report.invariance_violations == 0
    assert report.invariance_violation_rate == 0.0
    assert report.directional == report.directional_successes == 6
    assert report.directional_success_rate == 1.0


def test_an_invariance_miss_counts_a_violation_and_still_fails_exact_match():
    examples = build_behavioral_examples()
    casing_id = "auto-behavior-001-casing"
    casing = next(example for example in examples if example.id == casing_id)
    scored = score_example_output("267 miles", casing)
    report = summarize_behavioral_contracts(
        examples, _outcomes(examples, {casing_id: "267 miles"})
    )

    assert scored.passed is False
    assert scored.score == 0.0
    assert scored.scorer_details[0]["scorer"] == "exact_match"
    assert report.invariance_violations == 1
    assert report.invariance_violation_rate == pytest.approx(0.25)
    assert report.directional_success_rate == 1.0
    assert report.minimum_functionality_passed == 2


def test_a_directional_case_fails_when_it_keeps_the_original_answer():
    examples = build_behavioral_examples()
    numeric_id = "auto-behavior-001-numeric-evidence"
    report = summarize_behavioral_contracts(
        examples, _outcomes(examples, {numeric_id: "250 miles"})
    )

    assert report.directional_successes == 5
    assert report.directional_success_rate == pytest.approx(5 / 6)
    assert report.invariance_violations == 0


def test_report_outcomes_must_name_every_example_once():
    examples = build_behavioral_examples()[:2]

    with pytest.raises(BehavioralContractError, match="missing="):
        summarize_behavioral_contracts(examples, {examples[0].id: True})


@pytest.mark.parametrize(
    ("payloads", "match"),
    [
        (
            (
                _root(),
                {
                    **_root("src-casing"),
                    "contract": {"relation": "sideways", "source_example_id": "src"},
                },
            ),
            "Invalid dataset row",
        ),
        (
            (
                _root(),
                {
                    **_root("src-casing"),
                    "contract": {"relation": "invariance", "source_example_id": "missing"},
                },
            ),
            "missing source 'missing'",
        ),
        (
            (
                _root(),
                {
                    **_root("src-casing", split="holdout"),
                    "contract": {"relation": "invariance", "source_example_id": "src"},
                },
            ),
            "same split",
        ),
        (
            (
                _root("other"),
                {
                    **_root("src"),
                    "contract": {
                        "relation": "minimum_functionality",
                        "source_example_id": "other",
                    },
                },
            ),
            "must name itself",
        ),
        (
            (
                {
                    **_root("src"),
                    "contract": {"relation": "invariance", "source_example_id": "src"},
                },
            ),
            "cannot use itself",
        ),
        (
            (
                _root(),
                {
                    **_root("src-casing"),
                    "contract": {"relation": "invariance", "source_example_id": "src"},
                },
                {
                    **_root("src-casing-again"),
                    "contract": {
                        "relation": "directional",
                        "source_example_id": "src-casing",
                    },
                },
            ),
            "minimum-functionality source",
        ),
    ],
)
def test_malformed_behavioral_links_are_rejected(tmp_path, payloads, match):
    with pytest.raises(DatasetValidationError, match=match):
        load_jsonl(_write(tmp_path, *payloads))


def test_selecting_a_split_drops_a_perturbation_whose_source_is_absent():
    source = EvaluationExample.model_validate(_root())
    derived = EvaluationExample.model_validate(
        {
            **_root("src-casing", split="holdout"),
            "contract": {"relation": "invariance", "source_example_id": "src"},
        }
    )
    dataset = LoadedDataset(
        name="contracts",
        version="v1",
        examples=(source, derived),
        content_hash="unchecked",
    )

    with pytest.raises(DatasetValidationError, match="missing source 'src'"):
        dataset.select_split(EvaluationSplit.HOLDOUT)
