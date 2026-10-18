from pathlib import Path

import pytest

from evalbench.gates.sampler import (
    AdaptiveSampleError,
    SampledExample,
    SamplerPolicy,
    audit_adaptive_sample,
)

RUNNER_SOURCE = Path("evalbench/gates/runner.py")


def _example(
    example_id: str,
    tag: str,
    difficulty: str,
    candidate: float,
    *,
    baseline: float = 1.0,
    cost: float = 0.01,
):
    return SampledExample(
        example_id=example_id,
        tag=tag,
        difficulty=difficulty,
        baseline_score=baseline,
        candidate_score=candidate,
        estimated_cost_usd=cost,
    )


def test_a_uniform_regression_stops_after_coverage_and_matches_the_full_suite():
    examples = [
        _example("easy-extra", "range", "easy", 0.0),
        _example("hard-brake", "brake", "hard", 0.0),
        _example("hard-range", "range", "hard", 0.0),
        _example("easy-brake", "brake", "easy", 0.0),
    ]

    audit = audit_adaptive_sample(examples, SamplerPolicy(minimum_per_slice=1))
    repeated = audit_adaptive_sample(list(reversed(examples)), SamplerPolicy(minimum_per_slice=1))

    assert audit == repeated
    assert audit.sampling_order == ("hard-brake", "hard-range", "easy-brake", "easy-extra")
    assert audit.sampled_ids == ("hard-brake", "hard-range", "easy-brake")
    assert audit.stop_reason == "conclusive_interval"
    assert audit.adaptive_decision == audit.full_suite_decision == "regression"
    assert audit.decisions_agree is True
    assert audit.saved_calls == 1
    assert audit.model_call_count == 3
    assert audit.estimated_cost_usd == pytest.approx(0.03)
    assert audit.interval_history[-1].sample_size == 3
    assert audit.interval_history[-1].upper < 0
    assert [snapshot.sample_size for snapshot in audit.interval_history] == [2, 3]


def test_a_rare_slice_is_sampled_even_after_the_interval_is_already_decisive():
    examples = [
        _example("hard-brake", "brake", "hard", 0.0),
        _example("hard-range", "range", "hard", 0.0),
        _example("easy-brake", "brake", "easy", 0.0),
        _example("easy-rare", "towing", "easy", 0.0),
        _example("easy-spare", "towing", "easy", 0.0),
    ]

    audit = audit_adaptive_sample(examples, SamplerPolicy(minimum_per_slice=1))

    assert audit.sampled_ids[-1] == "easy-rare"
    assert "easy-spare" not in audit.sampled_ids
    assert audit.saved_calls == 1
    assert audit.decisions_agree is True


def test_disagreement_with_the_full_suite_does_not_report_saved_calls():
    early = [
        _example("hard-brake", "brake", "hard", 0.0),
        _example("hard-range", "range", "hard", 0.0),
        _example("easy-brake", "brake", "easy", 0.0),
    ]
    reversals = [
        _example(f"easy-reverse-{index}", "brake", "easy", 1.0, baseline=0.0)
        for index in range(6)
    ]

    audit = audit_adaptive_sample([*early, *reversals], SamplerPolicy(minimum_per_slice=1))

    assert audit.stop_reason == "conclusive_interval"
    assert audit.adaptive_decision == "regression"
    assert audit.full_suite_decision != "regression"
    assert audit.decisions_agree is False
    assert audit.saved_calls is None
    assert len(audit.sampling_order) > len(audit.sampled_ids)


def test_an_inconclusive_suite_is_read_in_full_and_saves_nothing():
    examples = [
        _example("hard-brake", "brake", "hard", 1.0),
        _example("easy-range", "range", "easy", 1.0),
    ]

    audit = audit_adaptive_sample(examples, SamplerPolicy(minimum_per_slice=1))

    assert audit.stop_reason == "full_suite"
    assert audit.sampled_ids == audit.sampling_order
    assert audit.adaptive_decision == audit.full_suite_decision == "inconclusive"
    assert audit.saved_calls == 0
    assert audit.model_call_count == 2


def test_the_release_gate_does_not_use_adaptive_stopping():
    assert "audit_adaptive_sample" not in RUNNER_SOURCE.read_text()


@pytest.mark.parametrize(
    ("examples", "policy", "match"),
    [
        ([], None, "at least two"),
        (
            [_example("one", "brake", "easy", 1.0), _example("one", "brake", "easy", 1.0)],
            None,
            "unique",
        ),
        (
            [_example("one", "brake", "easy", 1.0), _example("two", "brake", "odd", 1.0)],
            None,
            "difficulty",
        ),
        (
            [_example("one", "brake", "easy", 1.0), _example("two", "brake", "easy", 1.0)],
            SamplerPolicy(minimum_per_slice=0),
            "minimum_per_slice",
        ),
        (
            [_example("one", "brake", "easy", 1.0), _example("two", "brake", "easy", 1.0)],
            SamplerPolicy(minimum_detectable_effect=0),
            "minimum_detectable_effect",
        ),
    ],
)
def test_invalid_simulations_are_rejected(examples, policy, match):
    with pytest.raises(AdaptiveSampleError, match=match):
        audit_adaptive_sample(examples, policy)
