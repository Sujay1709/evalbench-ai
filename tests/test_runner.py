from dataclasses import replace
from uuid import UUID

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
        assert UUID(first_run.correlation_id)
        assert first_run.dataset_split == "development"
        assert first_run.total_examples == 3
        assert first_run.pass_rate == 1.0
        assert not any(result.cache_hit for result in first_run.results)

        assert second_run.status == "completed"
        assert second_run.mean_score == first_run.mean_score
        assert all(result.cache_hit for result in second_run.results)


def test_prepare_run_persists_queued_identity_without_provider_call(app):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
    ).select_split(EvaluationSplit.DEVELOPMENT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    class CountingProvider(MockProvider):
        calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()

    with app.app_context():
        run = EvaluationRunner(provider).prepare_run(dataset, prompt)

        assert run.status == "queued"
        assert run.dataset_split == "development"
        assert run.total_examples == 3
        assert UUID(run.correlation_id)
        assert provider.calls == 0


def test_prepare_run_reuses_explicit_correlation_id(app):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
    ).select_split(EvaluationSplit.DEVELOPMENT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")
    correlation_id = UUID("6f56c6b8-3338-4a2c-8f78-f98554051309")

    with app.app_context():
        runner = EvaluationRunner(MockProvider())
        first_run = runner.prepare_run(
            dataset,
            prompt,
            correlation_id=correlation_id,
        )
        replayed_run = runner.prepare_run(
            dataset,
            prompt,
            correlation_id=correlation_id,
        )

        assert replayed_run.id == first_run.id
        assert len(db.session.execute(db.select(EvaluationRun)).scalars().all()) == 1


def test_prepare_run_rejects_reused_correlation_for_different_request(app):
    loaded = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl")
    development = loaded.select_split(EvaluationSplit.DEVELOPMENT)
    holdout = loaded.select_split(EvaluationSplit.HOLDOUT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")
    correlation_id = UUID("b675073d-d5e5-4df2-9fef-e51cdf609a71")

    with app.app_context():
        runner = EvaluationRunner(MockProvider())
        runner.prepare_run(
            development,
            prompt,
            correlation_id=correlation_id,
        )

        with pytest.raises(ValueError, match="different evaluation request"):
            runner.prepare_run(
                holdout,
                prompt,
                correlation_id=correlation_id,
            )

        assert len(db.session.execute(db.select(EvaluationRun)).scalars().all()) == 1


def test_run_replay_with_same_correlation_returns_completed_run(app):
    dataset = load_jsonl(
        PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl"
    ).select_split(EvaluationSplit.DEVELOPMENT)
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")
    correlation_id = UUID("7923ee17-56de-49d0-9175-c68a9ce3c695")

    class CountingProvider(MockProvider):
        calls = 0

        def generate(self, prompt, example):
            self.calls += 1
            return super().generate(prompt, example)

    provider = CountingProvider()

    with app.app_context():
        runner = EvaluationRunner(provider)
        first_run = runner.run(dataset, prompt, correlation_id=correlation_id)
        replayed_run = runner.run(dataset, prompt, correlation_id=correlation_id)

        assert replayed_run.id == first_run.id
        assert replayed_run.status == "completed"
        assert provider.calls == 3


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
