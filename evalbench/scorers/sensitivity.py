"""Score whether answers move with named evidence, not only whether one string matches.

The report sits beside exact match, token F1, answerability, and schema scores.
A single supported-answer match cannot show that a system read the evidence.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from evalbench.datasets.sensitivity import (
    EvidenceFamily,
    EvidenceVariant,
    EvidenceVariantKind,
    ExpectedEvidenceBehavior,
    normalize_sensitivity_text,
)


class EvidenceSensitivityError(ValueError):
    """Outputs do not line up with the evidence family being scored."""


@dataclass(frozen=True)
class SensitivityFinding:
    """One variant's pass or failure, including the evidence edit that explains it."""

    variant_id: str
    kind: str
    changed_evidence_ids: tuple[str, ...]
    expected_behavior: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class SensitivityReport:
    passed: bool
    findings: tuple[SensitivityFinding, ...]


def evidence_insensitive_outputs(family: EvidenceFamily) -> dict[str, str]:
    """Repeat the supported answer no matter which evidence changed."""

    return {variant.id: family.supported_answer for variant in family.variants}


def evidence_responsive_outputs(family: EvidenceFamily) -> dict[str, str]:
    """Return the answer the family says that variant's evidence justifies."""

    return {variant.id: variant.expected_answer for variant in family.variants}


def score_evidence_sensitivity(
    family: EvidenceFamily, outputs: Mapping[str, str]
) -> SensitivityReport:
    """Explain every variant from its evidence IDs and expected behavior."""

    expected_ids = {variant.id for variant in family.variants}
    if set(outputs) != expected_ids:
        missing = sorted(expected_ids - set(outputs))
        extra = sorted(set(outputs) - expected_ids)
        raise EvidenceSensitivityError(
            "Sensitivity outputs must cover every evidence variant exactly once; "
            f"missing={missing}, extra={extra}"
        )

    findings = tuple(_finding(family, variant, outputs[variant.id]) for variant in family.variants)
    return SensitivityReport(
        passed=all(finding.passed for finding in findings),
        findings=findings,
    )


def _finding(family: EvidenceFamily, variant: EvidenceVariant, output: str) -> SensitivityFinding:
    expected = normalize_sensitivity_text(variant.expected_answer)
    actual = normalize_sensitivity_text(output)
    passed = actual == expected
    return SensitivityFinding(
        variant_id=variant.id,
        kind=variant.kind.value,
        changed_evidence_ids=tuple(variant.changed_evidence_ids),
        expected_behavior=variant.expected_behavior.value,
        passed=passed,
        evidence=_evidence(family, variant, output, passed),
    )


def _evidence(
    family: EvidenceFamily, variant: EvidenceVariant, output: str, passed: bool
) -> str:
    change = _change_phrase(variant)
    if variant.expected_behavior is ExpectedEvidenceBehavior.PRESERVATION:
        if passed:
            return f"Preserved '{family.supported_answer}'; {change}."
        return (
            f"Expected answer preservation of '{family.supported_answer}' because {change}, "
            f"but the output was '{output}'."
        )
    if variant.expected_behavior is ExpectedEvidenceBehavior.REVISION:
        if passed:
            return (
                f"Revised the answer from '{family.supported_answer}' to "
                f"'{variant.expected_answer}' after {change}."
            )
        kept_supported = normalize_sensitivity_text(output) == normalize_sensitivity_text(
            family.supported_answer
        )
        if kept_supported:
            return (
                f"Expected answer revision to '{variant.expected_answer}' after {change}, "
                f"but the output kept '{family.supported_answer}'."
            )
        return (
            f"Expected answer revision to '{variant.expected_answer}' after {change}, "
            f"but the output was '{output}'."
        )
    if passed:
        return f"Abstained with '{variant.expected_answer}' after {change}."
    return (
        f"Expected abstention '{variant.expected_answer}' after {change}, "
        f"but the output was '{output}'."
    )


def _change_phrase(variant: EvidenceVariant) -> str:
    evidence_ids = ", ".join(variant.changed_evidence_ids)
    if variant.kind is EvidenceVariantKind.SUPPORTED:
        return f"evidence {variant.evidence_id} is unchanged"
    if variant.kind is EvidenceVariantKind.EVIDENCE_REMOVED:
        return f"evidence {evidence_ids} was removed"
    if variant.kind is EvidenceVariantKind.VALUE_SWAPPED:
        return f"evidence {evidence_ids} was value-swapped"
    return f"evidence {evidence_ids} is contradictory"
