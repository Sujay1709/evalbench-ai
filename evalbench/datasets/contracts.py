"""Behavioral-contract checks and rates that sit beside ordinary example scores."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evalbench.datasets.schemas import BehavioralRelation, EvaluationExample


class BehavioralContractError(ValueError):
    """A dataset's perturbation links cannot be evaluated."""


def relation_of(example: EvaluationExample) -> BehavioralRelation:
    """Roots with no contract are the minimum-functionality cases."""

    if example.contract is None:
        return BehavioralRelation.MINIMUM_FUNCTIONALITY
    return example.contract.relation


def validate_behavioral_contracts(examples: Sequence[EvaluationExample]) -> None:
    """Reject links that would leak a perturbation across splits or hide its source."""

    by_id = {example.id: example for example in examples}
    for example in examples:
        contract = example.contract
        if contract is None:
            continue
        source = by_id.get(contract.source_example_id)
        if source is None:
            raise BehavioralContractError(
                f"Example '{example.id}' behavioral contract points at missing source "
                f"'{contract.source_example_id}'"
            )
        if source.split != example.split:
            raise BehavioralContractError(
                f"Example '{example.id}' is split '{example.split.value}' but behavioral "
                f"source '{source.id}' is split '{source.split.value}'. Keep a perturbation "
                "in the same split as its source."
            )
        if contract.relation is BehavioralRelation.MINIMUM_FUNCTIONALITY:
            if contract.source_example_id != example.id:
                raise BehavioralContractError(
                    f"Example '{example.id}' is a minimum-functionality case and must name "
                    "itself as the source"
                )
            continue
        if source.id == example.id:
            raise BehavioralContractError(
                f"Example '{example.id}' cannot use itself as an {contract.relation.value} source"
            )
        source_relation = relation_of(source)
        if source_relation is not BehavioralRelation.MINIMUM_FUNCTIONALITY:
            raise BehavioralContractError(
                f"Example '{example.id}' must link to a minimum-functionality source, "
                f"not derived example '{source.id}'"
            )


@dataclass(frozen=True)
class BehavioralContractReport:
    """Rates computed from existing pass/fail outcomes. They do not replace those scores."""

    minimum_functionality: int
    minimum_functionality_passed: int
    invariance: int
    invariance_violations: int
    directional: int
    directional_successes: int

    @property
    def invariance_violation_rate(self) -> float | None:
        if self.invariance == 0:
            return None
        return self.invariance_violations / self.invariance

    @property
    def directional_success_rate(self) -> float | None:
        if self.directional == 0:
            return None
        return self.directional_successes / self.directional


def summarize_behavioral_contracts(
    examples: Sequence[EvaluationExample],
    outcomes: Mapping[str, bool],
) -> BehavioralContractReport:
    """Count invariance violations and directional successes from ordinary pass bits."""

    example_ids = {example.id for example in examples}
    if set(outcomes) != example_ids:
        missing = sorted(example_ids - set(outcomes))
        extra = sorted(set(outcomes) - example_ids)
        raise BehavioralContractError(
            "Behavioral report outcomes must cover every example exactly once; "
            f"missing={missing}, extra={extra}"
        )

    counts = {
        BehavioralRelation.MINIMUM_FUNCTIONALITY: [0, 0],
        BehavioralRelation.INVARIANCE: [0, 0],
        BehavioralRelation.DIRECTIONAL: [0, 0],
    }
    for example in examples:
        total, matched = counts[relation_of(example)]
        passed = outcomes[example.id]
        counts[relation_of(example)] = [total + 1, matched + int(passed)]

    functionality = counts[BehavioralRelation.MINIMUM_FUNCTIONALITY]
    invariance = counts[BehavioralRelation.INVARIANCE]
    directional = counts[BehavioralRelation.DIRECTIONAL]
    return BehavioralContractReport(
        minimum_functionality=functionality[0],
        minimum_functionality_passed=functionality[1],
        invariance=invariance[0],
        invariance_violations=invariance[0] - invariance[1],
        directional=directional[0],
        directional_successes=directional[1],
    )
