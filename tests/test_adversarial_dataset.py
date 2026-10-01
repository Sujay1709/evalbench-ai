"""The adversarial automotive fixture stays deterministic and offline."""

import pytest

from evalbench.datasets import EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


@pytest.mark.parametrize("split", [EvaluationSplit.DEVELOPMENT, EvaluationSplit.HOLDOUT])
def test_adversarial_examples_have_explicit_deterministic_expected_outcomes(app, split):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "adversarial_v1.jsonl"
    ).select_split(split)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml")

    with app.app_context():
        run = EvaluationRunner(MockProvider()).run(dataset, prompt)
        run_split = run.dataset_split
        results = tuple((result.example_id, result.passed, result.score) for result in run.results)

    assert run_split == split.value
    assert len(results) == 2
    assert all(passed and score == 1 for _, passed, score in results)
    tags_by_id = {example.id: example.tags for example in dataset.examples}
    assert all("adversarial" in tags_by_id[example_id] for example_id, _, _ in results)
    with app.app_context():
        db.session.remove()
