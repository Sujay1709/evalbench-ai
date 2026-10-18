"""Deterministic automotive perturbations for behavioral contracts.

Each derived example keeps its own exact-match scorer. Invariance cases must
keep the source answer. Directional cases must follow the changed evidence
or abstain. The generator does not alter exact-match, token F1, answerability,
or schema scoring.
"""

import re

from evalbench.datasets.schemas import (
    BehavioralContract,
    BehavioralRelation,
    EvaluationExample,
    EvaluationSplit,
    ScorerSpec,
)

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NUMBER_SHIFT = 17
ABSTENTION = "Insufficient evidence"

PERTURBATION_KINDS = (
    "casing",
    "harmless-wording",
    "numeric-evidence",
    "missing-evidence",
    "contradictory-evidence",
)


def _exact_expected(example: EvaluationExample) -> str:
    for spec in example.scorers:
        if spec.type == "exact_match" and spec.expected is not None:
            return spec.expected
    raise ValueError(
        f"Example '{example.id}' needs an exact_match expectation before it can be perturbed"
    )


def _require_text(example: EvaluationExample, field: str) -> str:
    value = example.input.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Example '{example.id}' needs a non-empty input.{field} to perturb")
    return value


def _shift_number(raw: str) -> str:
    if "." in raw:
        return f"{float(raw) + _NUMBER_SHIFT:.1f}"
    return str(int(raw) + _NUMBER_SHIFT)


def _first_number(text: str) -> re.Match[str]:
    match = _NUMBER.search(text)
    if match is None:
        raise ValueError("A numeric-evidence perturbation needs a number in the source text")
    return match


def _replace_first_number(text: str, replacement: str) -> str:
    match = _first_number(text)
    return text[: match.start()] + replacement + text[match.end() :]


def _derived(
    source: EvaluationExample,
    kind: str,
    relation: BehavioralRelation,
    *,
    question: str,
    evidence: str,
    expected: str,
) -> EvaluationExample:
    return source.model_copy(
        update={
            "id": f"{source.id}-{kind}",
            "input": {**source.input, "question": question, "evidence": evidence},
            "mock_response": expected,
            "scorers": [ScorerSpec(type="exact_match", expected=expected)],
            "tags": [*source.tags, "behavioral-contract", kind],
            "contract": BehavioralContract(
                relation=relation, source_example_id=source.id
            ),
        }
    )


def automotive_perturbations(source: EvaluationExample) -> tuple[EvaluationExample, ...]:
    """Return the five linked cases for one capability example, in a fixed order."""

    if relation_is_derived(source):
        raise ValueError(
            f"Example '{source.id}' is already derived. Perturb a minimum-functionality source."
        )
    question = _require_text(source, "question")
    evidence = _require_text(source, "evidence")
    expected = _exact_expected(source)
    number = _first_number(evidence)
    if number.group(0) not in expected:
        raise ValueError(
            f"Example '{source.id}' expected answer must contain evidence number "
            f"'{number.group(0)}' so the directional case stays deterministic"
        )
    shifted = _shift_number(number.group(0))
    invariance = BehavioralRelation.INVARIANCE
    directional = BehavioralRelation.DIRECTIONAL
    return (
        _derived(
            source,
            "casing",
            invariance,
            question=question.upper(),
            evidence=evidence,
            expected=expected,
        ),
        _derived(
            source,
            "harmless-wording",
            invariance,
            question=f"Please answer this: {question}",
            evidence=evidence,
            expected=expected,
        ),
        _derived(
            source,
            "numeric-evidence",
            directional,
            question=question,
            evidence=_replace_first_number(evidence, shifted),
            expected=_replace_first_number(expected, shifted),
        ),
        _derived(
            source,
            "missing-evidence",
            directional,
            question=question,
            evidence="",
            expected=ABSTENTION,
        ),
        _derived(
            source,
            "contradictory-evidence",
            directional,
            question=question,
            evidence=(
                f"{evidence} A conflicting service note lists the value as {shifted}."
            ),
            expected=ABSTENTION,
        ),
    )


def relation_is_derived(example: EvaluationExample) -> bool:
    return (
        example.contract is not None
        and example.contract.relation is not BehavioralRelation.MINIMUM_FUNCTIONALITY
    )


def behavioral_fixture_sources() -> tuple[EvaluationExample, ...]:
    """Two authored capability cases, one per split, that the perturbations derive from."""

    return (
        EvaluationExample(
            id="auto-behavior-001",
            input={
                "question": "What is the rated range of the sample EV?",
                "evidence": "The sample EV has a rated range of 250 miles.",
                "response_format": "Return only the range and unit.",
            },
            mock_response="250 miles",
            scorers=[ScorerSpec(type="exact_match", expected="250 miles")],
            tags=["ev", "range"],
            difficulty="easy",
            split=EvaluationSplit.DEVELOPMENT,
        ),
        EvaluationExample(
            id="auto-behavior-002",
            input={
                "question": "What is the sample sedan's city fuel economy?",
                "evidence": "The sample sedan is rated at 32 mpg in the city.",
                "response_format": "Return only the economy and unit.",
            },
            mock_response="32 mpg",
            scorers=[ScorerSpec(type="exact_match", expected="32 mpg")],
            tags=["efficiency", "economy"],
            difficulty="easy",
            split=EvaluationSplit.HOLDOUT,
        ),
    )


def build_behavioral_examples() -> tuple[EvaluationExample, ...]:
    """Capability cases followed by their perturbations, grouped by source."""

    examples: list[EvaluationExample] = []
    for source in behavioral_fixture_sources():
        examples.append(source)
        examples.extend(automotive_perturbations(source))
    return tuple(examples)
