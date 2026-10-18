"""Decide whether a judge may participate in a release gate.

The passport collects evidence the judge stack already knows how to measure:
rubric identity, repeated scoring, order-swap flip rate, holdout agreement, and
a verbosity probe. Missing evidence refuses the gate. Deterministic scorers stay
authoritative for properties they can check directly. A passport that passes
these thresholds is a check on the supplied evidence, not a measured claim that
a judge is reliable on a real holdout.
"""

from dataclasses import dataclass
from typing import Protocol

from evalbench.judges.calibration import CalibrationReport
from evalbench.judges.calibration_gate import (
    CalibrationReadinessPolicy,
    assess_calibration_readiness,
)
from evalbench.judges.pairwise import PairwiseOrderSwapReport
from evalbench.judges.repeatability import RepeatabilityReport


class JudgeDeclaration(Protocol):
    """The gate config fields a passport must match. Kept structural to avoid an import cycle."""

    judge_id: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str


@dataclass(frozen=True)
class JudgePassportPolicy:
    """Release-gate thresholds for supplied judge evidence."""

    minimum_repeatability: float = 1.0
    maximum_order_flip_rate: float = 0.0


@dataclass(frozen=True)
class VerbosityProbe:
    """Ratings of the same answer content at two lengths."""

    criterion_ids: tuple[str, ...]
    short_ratings: tuple[int, ...]
    long_ratings: tuple[int, ...]


@dataclass(frozen=True)
class PassportSection:
    name: str
    passed: bool
    evidence: str


@dataclass(frozen=True)
class JudgePassport:
    judge_id: str
    rubric_id: str
    rubric_version: str
    rubric_hash: str
    sections: tuple[PassportSection, ...]

    @property
    def allows_release_gate(self) -> bool:
        return all(section.passed for section in self.sections)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            f"{section.name}: {section.evidence}"
            for section in self.sections
            if not section.passed
        )


def build_judge_passport(
    *,
    judge_id: str,
    rubric_id: str,
    rubric_version: str,
    rubric_hash: str,
    repeatability: RepeatabilityReport | None = None,
    order_swaps: PairwiseOrderSwapReport | None = None,
    calibration_report: CalibrationReport | None = None,
    calibration_split: str | None = None,
    verbosity: VerbosityProbe | None = None,
    deterministic_scores_remain_authoritative: bool = True,
    readiness_policy: CalibrationReadinessPolicy | None = None,
    passport_policy: JudgePassportPolicy | None = None,
) -> JudgePassport:
    """Assemble every required section, including the ones with no evidence yet."""

    policy = passport_policy or JudgePassportPolicy()
    readiness = readiness_policy or CalibrationReadinessPolicy()
    sections = (
        _rubric_section(judge_id, rubric_id, rubric_version, rubric_hash),
        _repeatability_section(judge_id, rubric_hash, repeatability, policy),
        _order_swap_section(judge_id, rubric_id, rubric_version, rubric_hash, order_swaps, policy),
        _agreement_section(
            rubric_hash, calibration_report, calibration_split, readiness
        ),
        _verbosity_section(verbosity),
        _authority_section(deterministic_scores_remain_authoritative),
    )
    return JudgePassport(
        judge_id=judge_id,
        rubric_id=rubric_id,
        rubric_version=rubric_version,
        rubric_hash=rubric_hash,
        sections=sections,
    )


def release_gate_block(
    passport: JudgePassport | None, declaration: JudgeDeclaration | None
) -> str | None:
    """Return why a judge must not affect the release gate, or None to continue."""

    if declaration is None:
        if passport is None:
            return None
        return (
            "The regression gate scores deterministic checks. "
            "A judge passport cannot authorize it."
        )
    if passport is None:
        return (
            f"Judge '{declaration.judge_id}' cannot participate in the release gate: "
            "no passport was supplied"
        )
    if not passport.allows_release_gate:
        return (
            f"Judge '{declaration.judge_id}' cannot participate in the release gate: "
            + "; ".join(passport.failures)
        )
    if (
        passport.judge_id != declaration.judge_id
        or passport.rubric_id != declaration.rubric_id
        or passport.rubric_version != declaration.rubric_version
        or passport.rubric_hash != declaration.rubric_hash
    ):
        return "Judge passport does not match the judge declared by the gate config"
    return None


def _rubric_section(
    judge_id: str, rubric_id: str, rubric_version: str, rubric_hash: str
) -> PassportSection:
    valid_hash = len(rubric_hash) == 64 and set(rubric_hash) <= set("0123456789abcdef")
    named = all(value.strip() for value in (judge_id, rubric_id, rubric_version))
    passed = valid_hash and named
    if passed:
        evidence = f"Rubric {rubric_id}@{rubric_version} hash {rubric_hash} for judge {judge_id}."
    else:
        evidence = "Rubric identity needs a judge id, rubric id, version, and 64-character hash."
    return PassportSection("rubric", passed, evidence)


def _repeatability_section(
    judge_id: str,
    rubric_hash: str,
    report: RepeatabilityReport | None,
    policy: JudgePassportPolicy,
) -> PassportSection:
    if report is None:
        return PassportSection(
            "repeatability", False, "Repeated scoring of the same request was not supplied."
        )
    if report.judge_model != judge_id or report.rubric_hash != rubric_hash:
        return PassportSection(
            "repeatability",
            False,
            "Repeatability evidence is for a different judge or rubric.",
        )
    passed = report.exact_agreement >= policy.minimum_repeatability
    evidence = (
        f"Exact agreement {report.exact_agreement:.3f} across {report.rating_pair_count} "
        f"rating pairs (minimum {policy.minimum_repeatability:.3f}) on rubric {rubric_hash}."
    )
    if not passed:
        evidence = f"Repeated scores disagreed. {evidence}"
    return PassportSection("repeatability", passed, evidence)


def _order_swap_section(
    judge_id: str,
    rubric_id: str,
    rubric_version: str,
    rubric_hash: str,
    report: PairwiseOrderSwapReport | None,
    policy: JudgePassportPolicy,
) -> PassportSection:
    if report is None:
        return PassportSection(
            "order_swaps", False, "Order-swapped pairwise judgments were not supplied."
        )
    if report.judge_model != judge_id or (
        report.rubric_id,
        report.rubric_version,
        report.rubric_hash,
    ) != (rubric_id, rubric_version, rubric_hash):
        return PassportSection(
            "order_swaps", False, "Order-swap evidence is for a different judge or rubric."
        )
    if report.dataset_split != "holdout":
        return PassportSection(
            "order_swaps",
            False,
            "Order-swap evidence must come from the holdout split.",
        )
    passed = report.preference_flip_rate <= policy.maximum_order_flip_rate
    evidence = (
        f"Preference flip rate {report.preference_flip_rate:.3f} on {report.comparison_count} "
        f"holdout comparisons (maximum {policy.maximum_order_flip_rate:.3f})."
    )
    if not passed:
        evidence = f"Answer order changed a preference. {evidence}"
    return PassportSection("order_swaps", passed, evidence)


def _agreement_section(
    rubric_hash: str,
    report: CalibrationReport | None,
    dataset_split: str | None,
    policy: CalibrationReadinessPolicy,
) -> PassportSection:
    if report is None or dataset_split is None:
        return PassportSection(
            "human_agreement",
            False,
            "No human-reviewed holdout agreement is attached, so this judge cannot gate a release.",
        )
    if report.rubric_hash != rubric_hash:
        return PassportSection(
            "human_agreement", False, "Human agreement was computed for a different rubric hash."
        )
    readiness = assess_calibration_readiness(report, dataset_split=dataset_split, policy=policy)
    matrix = report.overall.confusion_matrix
    evidence = "; ".join((*readiness.checks, f"confusion matrix {matrix}"))
    if readiness.failures:
        evidence = f"{'; '.join(readiness.failures)}. {evidence}"
    return PassportSection("human_agreement", readiness.eligible, evidence)


def _verbosity_section(probe: VerbosityProbe | None) -> PassportSection:
    if probe is None:
        return PassportSection(
            "verbosity", False, "A short-versus-long rating probe was not supplied."
        )
    if (
        not probe.criterion_ids
        or len(set(probe.criterion_ids)) != len(probe.criterion_ids)
        or len(probe.short_ratings) != len(probe.criterion_ids)
        or len(probe.long_ratings) != len(probe.criterion_ids)
        or any(type(score) is not int or score not in (0, 1, 2) for score in probe.short_ratings)
        or any(type(score) is not int or score not in (0, 1, 2) for score in probe.long_ratings)
    ):
        return PassportSection(
            "verbosity",
            False,
            "Verbosity ratings must be 0, 1, or 2 for each unique rubric criterion.",
        )
    changed = [
        criterion_id
        for criterion_id, short, long in zip(
            probe.criterion_ids, probe.short_ratings, probe.long_ratings, strict=True
        )
        if short != long
    ]
    if changed:
        details = ", ".join(
            f"{criterion_id} {short} to {long}"
            for criterion_id, short, long in zip(
                probe.criterion_ids, probe.short_ratings, probe.long_ratings, strict=True
            )
            if short != long
        )
        return PassportSection(
            "verbosity",
            False,
            f"Lengthening the answer changed ratings: {details}.",
        )
    names = ", ".join(probe.criterion_ids)
    return PassportSection(
        "verbosity", True, f"Short and long ratings matched on {names}."
    )


def _authority_section(deterministic_scores_remain_authoritative: bool) -> PassportSection:
    if deterministic_scores_remain_authoritative:
        return PassportSection(
            "authority",
            True,
            "Exact match, token F1, answerability, and schema scores stay authoritative.",
        )
    return PassportSection(
        "authority",
        False,
        "A judge cannot replace exact match, token F1, answerability, or schema scores.",
    )
