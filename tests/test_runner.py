from dataclasses import replace

import pytest

from evalbench.datasets import DatasetSplitError, EvaluationSplit, load_jsonl
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


def test_second_run_reuses_cached_responses(app):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
    ).select_split(EvaluationSplit.DEVELOPMENT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    with app.app_context():
        runner = EvaluationRunner(MockProvider())
        first_run = runner.run(dataset, prompt)
        second_run = runner.run(dataset, prompt)

        assert first_run.status == "completed"
        assert first_run.dataset_split == "development"
        assert first_run.total_examples == 3
        assert first_run.pass_rate == 1.0
        assert not any(result.cache_hit for result in first_run.results)

        assert second_run.status == "completed"
        assert second_run.mean_score == first_run.mean_score
        assert all(result.cache_hit for result in second_run.results)


@pytest.mark.parametrize(
    ("relative_path", "split"),
    [
        ("datasets/squad_v2/sample_v1.jsonl", EvaluationSplit.DEVELOPMENT),
        ("datasets/squad_v2/sample_v1.jsonl", EvaluationSplit.HOLDOUT),
        ("datasets/hotpot_qa/sample_v1.jsonl", EvaluationSplit.DEVELOPMENT),
        ("datasets/hotpot_qa/sample_v1.jsonl", EvaluationSplit.HOLDOUT),
    ],
)
def test_external_sample_runs_end_to_end(app, relative_path, split):
    dataset = load_jsonl(PROJECT_ROOT / relative_path).select_split(split)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "grounded_qa" / "v1.yaml")

    with app.app_context():
        run = EvaluationRunner(MockProvider()).run(dataset, prompt)

        assert run.status == "completed"
        assert run.dataset_split == split.value
        assert run.total_examples == 2
        assert run.passed_examples == 2
        assert run.pass_rate == 1.0
        assert len(run.results) == 2


def test_runner_rejects_unselected_dataset_before_persistence_or_provider_call(app):
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl")
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    class CountingProvider(MockProvider):
        calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()

    with app.app_context():
        with pytest.raises(DatasetSplitError, match="must be selected"):
            EvaluationRunner(provider).run(dataset, prompt)

        assert provider.calls == 0
        assert db.session.execute(db.select(EvaluationRun)).scalars().all() == []


def test_runner_rejects_mixed_labels_in_a_selected_dataset(app):
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl")
    malformed_selection = replace(
        dataset,
        selected_split=EvaluationSplit.DEVELOPMENT,
    )
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    with app.app_context():
        with pytest.raises(DatasetSplitError, match="contains mixed split labels"):
            EvaluationRunner(MockProvider()).run(malformed_selection, prompt)

        assert db.session.execute(db.select(EvaluationRun)).scalars().all() == []
