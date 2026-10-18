import json

import pytest
from pydantic import ValidationError

from evalbench.datasets import (
    EvaluationSplit,
    EvidenceFamilyError,
    ScorerSpec,
    automotive_evidence_family,
    evidence_family_hash,
    load_evidence_family,
)
from evalbench.datasets.sensitivity import EvidenceFamily, EvidenceVariant
from evalbench.scorers import (
    evidence_insensitive_outputs,
    evidence_responsive_outputs,
    score_evidence_sensitivity,
    score_response,
)
from evalbench.scorers.sensitivity import EvidenceSensitivityError
from tests.conftest import PROJECT_ROOT

FAMILY_PATH = PROJECT_ROOT / "datasets" / "automotive_qa" / "sensitivity_v1.json"


def _variant(family: EvidenceFamily, kind: str):
    return next(variant for variant in family.variants if variant.kind.value == kind)


def test_sensitivity_fixture_matches_the_generator_and_keeps_a_stable_hash():
    loaded = load_evidence_family(FAMILY_PATH)
    generated = automotive_evidence_family()

    assert loaded.model_dump(mode="json") == generated.model_dump(mode="json")
    assert evidence_family_hash(loaded) == evidence_family_hash(generated)
    assert len(evidence_family_hash(loaded)) == 64
    assert loaded.split is EvaluationSplit.DEVELOPMENT
    assert json.loads(FAMILY_PATH.read_text()) == generated.model_dump(mode="json")


def test_family_records_the_evidence_edit_and_expected_behavior():
    family = automotive_evidence_family()
    supported = _variant(family, "supported")
    removed = _variant(family, "evidence_removed")
    swapped = _variant(family, "value_swapped")
    contradictory = _variant(family, "contradictory")

    assert supported.changed_evidence_ids == []
    assert supported.expected_behavior.value == "answer_preservation"
    assert removed.changed_evidence_ids == ["charge-test"]
    assert removed.context == ""
    assert removed.expected_behavior.value == "abstention"
    assert swapped.expected_answer == "41 minutes"
    assert swapped.expected_behavior.value == "answer_revision"
    assert "41" in swapped.context
    assert contradictory.expected_behavior.value == "abstention"
    assert "28" in contradictory.context and "19" in contradictory.context


def test_an_evidence_insensitive_system_fails_and_a_responsive_fixture_passes():
    family = automotive_evidence_family()
    insensitive = score_evidence_sensitivity(family, evidence_insensitive_outputs(family))
    responsive = score_evidence_sensitivity(family, evidence_responsive_outputs(family))
    exact = score_response(
        family.supported_answer,
        ScorerSpec(type="exact_match", expected=family.supported_answer),
    )

    assert exact.passed is True
    assert exact.scorer == "exact_match"
    assert insensitive.passed is False
    assert responsive.passed is True
    by_kind = {finding.kind: finding for finding in insensitive.findings}
    assert by_kind["supported"].passed is True
    assert by_kind["supported"].changed_evidence_ids == ()
    assert "charge-test is unchanged" in by_kind["supported"].evidence
    assert by_kind["evidence_removed"].passed is False
    assert by_kind["evidence_removed"].changed_evidence_ids == ("charge-test",)
    assert "charge-test was removed" in by_kind["evidence_removed"].evidence
    assert "28 minutes" in by_kind["evidence_removed"].evidence
    assert by_kind["value_swapped"].passed is False
    assert "kept '28 minutes'" in by_kind["value_swapped"].evidence
    assert "41 minutes" in by_kind["value_swapped"].evidence
    assert by_kind["contradictory"].passed is False
    assert "contradictory" in by_kind["contradictory"].evidence
    assert all(finding.evidence for finding in responsive.findings)
    assert all(finding.passed for finding in responsive.findings)
    assert "Revised the answer from '28 minutes' to '41 minutes'" in next(
        finding.evidence for finding in responsive.findings if finding.kind == "value_swapped"
    )


def test_whitespace_and_case_still_count_as_following_the_evidence():
    family = automotive_evidence_family()
    outputs = evidence_responsive_outputs(family)
    removed = _variant(family, "evidence_removed")
    outputs[removed.id] = "  insufficient   evidence "

    report = score_evidence_sensitivity(family, outputs)

    assert report.passed is True


def test_a_revision_to_the_wrong_value_explains_the_mismatch():
    family = automotive_evidence_family()
    outputs = evidence_responsive_outputs(family)
    swapped = _variant(family, "value_swapped")
    outputs[swapped.id] = "19 minutes"

    report = score_evidence_sensitivity(family, outputs)
    finding = next(item for item in report.findings if item.variant_id == swapped.id)

    assert report.passed is False
    assert finding.passed is False
    assert "output was '19 minutes'" in finding.evidence
    assert finding.expected_behavior == "answer_revision"


def test_outputs_must_cover_every_variant_once():
    family = automotive_evidence_family()
    outputs = evidence_responsive_outputs(family)
    removed = outputs.pop(_variant(family, "evidence_removed").id)
    outputs["extra"] = removed

    with pytest.raises(EvidenceSensitivityError, match="missing=.*extra="):
        score_evidence_sensitivity(family, outputs)


def test_missing_and_invalid_family_files_are_rejected(tmp_path):
    with pytest.raises(EvidenceFamilyError, match="not found"):
        load_evidence_family(tmp_path / "missing.json")

    invalid = tmp_path / "broken.json"
    invalid.write_text("{")
    with pytest.raises(EvidenceFamilyError, match="Invalid evidence family"):
        load_evidence_family(invalid)


def _family_payload(**updates):
    payload = automotive_evidence_family().model_dump(mode="json")
    payload.update(updates)
    return payload


def _variants():
    return automotive_evidence_family().model_dump(mode="json")["variants"]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        ("drop-kind", "exactly one"),
        ("supported-change", "cannot list changes"),
        ("revision-same-answer", "must revise"),
        ("removed-context", "empty context"),
        ("duplicate-id", "must be unique"),
        ("swap-keeps-old-number", "must replace the supported value"),
        ("behavior-mismatch", "requires expected behavior"),
    ],
)
def test_incomplete_evidence_contrasts_are_rejected(mutate, match):
    payload = automotive_evidence_family().model_dump(mode="json")
    variants = payload["variants"]
    if mutate == "drop-kind":
        variants[1]["kind"] = "supported"
    elif mutate == "supported-change":
        variants[0]["changed_evidence_ids"] = ["charge-test"]
    elif mutate == "revision-same-answer":
        variants[2]["expected_answer"] = payload["supported_answer"]
        variants[2]["context"] = variants[0]["context"].replace("28", "28")
    elif mutate == "removed-context":
        variants[1]["context"] = "Some leftover context with 28 minutes."
    elif mutate == "duplicate-id":
        variants[3]["id"] = variants[0]["id"]
    elif mutate == "swap-keeps-old-number":
        variants[2]["context"] = "The card says 28 minutes and also 41 minutes."
    elif mutate == "behavior-mismatch":
        variants[2]["expected_behavior"] = "abstention"
    else:
        raise AssertionError(mutate)

    with pytest.raises(ValidationError, match=match):
        EvidenceFamily.model_validate(payload)


def test_a_variant_must_name_the_evidence_it_changes():
    payload = automotive_evidence_family().model_dump(mode="json")
    payload["variants"][1]["changed_evidence_ids"] = ["other-card"]

    with pytest.raises(ValidationError, match="must list evidence 'charge-test'"):
        EvidenceFamily.model_validate(payload)


def test_evidence_variant_rejects_a_blank_answer():
    source = automotive_evidence_family().variants[0]

    with pytest.raises(ValidationError):
        EvidenceVariant(
            id=source.id,
            kind=source.kind,
            evidence_id=source.evidence_id,
            context=source.context,
            expected_behavior=source.expected_behavior,
            expected_answer="  ",
        )
