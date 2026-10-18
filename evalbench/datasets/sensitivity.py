"""Counterfactual evidence families for one question.

A family states which evidence IDs changed and whether the answer should stay,
change, or be withheld. It does not score a system; the sensitivity scorer does.
"""

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from evalbench.datasets.schemas import EvaluationSplit

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class EvidenceFamilyError(ValueError):
    """An evidence family cannot be loaded or does not state a complete contrast."""


class EvidenceVariantKind(StrEnum):
    SUPPORTED = "supported"
    EVIDENCE_REMOVED = "evidence_removed"
    VALUE_SWAPPED = "value_swapped"
    CONTRADICTORY = "contradictory"


class ExpectedEvidenceBehavior(StrEnum):
    PRESERVATION = "answer_preservation"
    REVISION = "answer_revision"
    ABSTENTION = "abstention"


_BEHAVIOR_BY_KIND = {
    EvidenceVariantKind.SUPPORTED: ExpectedEvidenceBehavior.PRESERVATION,
    EvidenceVariantKind.EVIDENCE_REMOVED: ExpectedEvidenceBehavior.ABSTENTION,
    EvidenceVariantKind.VALUE_SWAPPED: ExpectedEvidenceBehavior.REVISION,
    EvidenceVariantKind.CONTRADICTORY: ExpectedEvidenceBehavior.ABSTENTION,
}


def normalize_sensitivity_text(value: str) -> str:
    """Match exact-match comparison: trim, collapse whitespace, and casefold."""

    return re.sub(r"\s+", " ", value.strip()).casefold()


class EvidenceVariant(BaseModel):
    """One context for the family's question, with the evidence edit made explicit."""

    id: str = Field(min_length=1, max_length=120)
    kind: EvidenceVariantKind
    evidence_id: str = Field(min_length=1, max_length=120)
    changed_evidence_ids: list[str] = Field(default_factory=list)
    context: str
    expected_behavior: ExpectedEvidenceBehavior
    expected_answer: str = Field(min_length=1)

    @field_validator("expected_answer")
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("expected_answer must contain non-whitespace text")
        return value


class EvidenceFamily(BaseModel):
    """Supported evidence plus the three counterfactuals for a single question."""

    id: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1)
    supported_answer: str = Field(min_length=1)
    split: EvaluationSplit = EvaluationSplit.DEVELOPMENT
    variants: list[EvidenceVariant] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def require_a_complete_contrast(self) -> "EvidenceFamily":
        kinds = [variant.kind for variant in self.variants]
        if set(kinds) != set(EvidenceVariantKind):
            raise ValueError(
                "An evidence family needs exactly one supported, evidence_removed, "
                "value_swapped, and contradictory variant"
            )
        variant_ids = [variant.id for variant in self.variants]
        if len(set(variant_ids)) != len(variant_ids):
            raise ValueError("Evidence variant ids must be unique")

        supported = next(
            variant for variant in self.variants if variant.kind is EvidenceVariantKind.SUPPORTED
        )
        supported_number = _first_number(supported.context, "supported context")
        if normalize_sensitivity_text(supported.expected_answer) != normalize_sensitivity_text(
            self.supported_answer
        ):
            raise ValueError("The supported variant must expect the family's supported answer")
        if supported_number not in self.supported_answer:
            raise ValueError("The supported answer must contain the number stated in its evidence")

        for variant in self.variants:
            _validate_changed_ids(variant)
            if variant.expected_behavior is not _BEHAVIOR_BY_KIND[variant.kind]:
                raise ValueError(
                    f"Variant '{variant.id}' kind '{variant.kind.value}' requires expected "
                    f"behavior '{_BEHAVIOR_BY_KIND[variant.kind].value}'"
                )
            if variant.kind is EvidenceVariantKind.SUPPORTED:
                if variant.changed_evidence_ids:
                    raise ValueError(
                        f"Variant '{variant.id}' is supported evidence and cannot list changes"
                    )
                if not variant.context.strip():
                    raise ValueError(f"Variant '{variant.id}' needs supported context")
                continue
            if variant.evidence_id not in variant.changed_evidence_ids:
                raise ValueError(
                    f"Variant '{variant.id}' must list evidence '{variant.evidence_id}' as changed"
                )
            if variant.kind is EvidenceVariantKind.EVIDENCE_REMOVED:
                if variant.context.strip():
                    raise ValueError(
                        f"Variant '{variant.id}' removes evidence and must use an empty context"
                    )
            elif variant.kind is EvidenceVariantKind.VALUE_SWAPPED:
                revised = _first_number(
                    variant.expected_answer, f"variant '{variant.id}' answer"
                )
                same_answer = normalize_sensitivity_text(
                    variant.expected_answer
                ) == normalize_sensitivity_text(self.supported_answer)
                if same_answer:
                    raise ValueError(f"Variant '{variant.id}' must revise the supported answer")
                if revised == supported_number or revised not in variant.context:
                    raise ValueError(
                        f"Variant '{variant.id}' context must state the revised value '{revised}'"
                    )
                if supported_number in variant.context:
                    raise ValueError(
                        f"Variant '{variant.id}' context must replace the supported value "
                        f"'{supported_number}'"
                    )
            elif supported_number not in variant.context or not _has_other_number(
                variant.context, supported_number
            ):
                raise ValueError(
                    f"Variant '{variant.id}' context must state both the supported value and a "
                    "conflicting value"
                )
        return self


def _validate_changed_ids(variant: EvidenceVariant) -> None:
    if any(not evidence_id.strip() for evidence_id in variant.changed_evidence_ids):
        raise ValueError(f"Variant '{variant.id}' has an empty changed evidence id")
    if len(set(variant.changed_evidence_ids)) != len(variant.changed_evidence_ids):
        raise ValueError(f"Variant '{variant.id}' repeats a changed evidence id")


def _first_number(text: str, label: str) -> str:
    match = _NUMBER.search(text)
    if match is None:
        raise ValueError(f"{label} needs a number so the evidence change is observable")
    return match.group(0)


def _has_other_number(text: str, original: str) -> bool:
    return any(number != original for number in _NUMBER.findall(text))


def evidence_family_hash(family: EvidenceFamily) -> str:
    """Hash the canonical family so a fixture edit is visible."""

    payload = family.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def load_evidence_family(path: str | Path) -> EvidenceFamily:
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise EvidenceFamilyError(f"Evidence family not found: {dataset_path}")
    try:
        return EvidenceFamily.model_validate_json(dataset_path.read_text())
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceFamilyError(f"Invalid evidence family: {exc}") from exc


def automotive_evidence_family() -> EvidenceFamily:
    """One development question whose answer is determined by a single evidence card."""

    family_id = "auto-sensitivity-001"
    evidence_id = "charge-test"
    question = "What is the sample EV's DC fast-charge time from 10% to 80%?"
    supported_context = "Charge test: the sample EV's DC fast charge took 28 minutes."
    supported_answer = "28 minutes"
    return EvidenceFamily(
        id=family_id,
        question=question,
        supported_answer=supported_answer,
        split=EvaluationSplit.DEVELOPMENT,
        variants=[
            EvidenceVariant(
                id=f"{family_id}-supported",
                kind=EvidenceVariantKind.SUPPORTED,
                evidence_id=evidence_id,
                changed_evidence_ids=[],
                context=supported_context,
                expected_behavior=ExpectedEvidenceBehavior.PRESERVATION,
                expected_answer=supported_answer,
            ),
            EvidenceVariant(
                id=f"{family_id}-evidence-removed",
                kind=EvidenceVariantKind.EVIDENCE_REMOVED,
                evidence_id=evidence_id,
                changed_evidence_ids=[evidence_id],
                context="",
                expected_behavior=ExpectedEvidenceBehavior.ABSTENTION,
                expected_answer="Insufficient evidence",
            ),
            EvidenceVariant(
                id=f"{family_id}-value-swapped",
                kind=EvidenceVariantKind.VALUE_SWAPPED,
                evidence_id=evidence_id,
                changed_evidence_ids=[evidence_id],
                context="Charge test: the sample EV's DC fast charge took 41 minutes.",
                expected_behavior=ExpectedEvidenceBehavior.REVISION,
                expected_answer="41 minutes",
            ),
            EvidenceVariant(
                id=f"{family_id}-contradictory",
                kind=EvidenceVariantKind.CONTRADICTORY,
                evidence_id=evidence_id,
                changed_evidence_ids=[evidence_id],
                context=(
                    f"{supported_context} A second lab note lists 19 minutes for the same test."
                ),
                expected_behavior=ExpectedEvidenceBehavior.ABSTENTION,
                expected_answer="Insufficient evidence",
            ),
        ],
    )
