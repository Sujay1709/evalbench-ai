from evalbench.datasets import load_jsonl
from evalbench.prompts import load_prompt
from evalbench.providers import MockProvider
from evalbench.runners import EvaluationRunner
from tests.conftest import PROJECT_ROOT


def test_second_run_reuses_cached_responses(app):
    dataset = load_jsonl(PROJECT_ROOT / "datasets" / "automotive_qa" / "v1.jsonl")
    prompt = load_prompt(PROJECT_ROOT / "prompts" / "automotive_qa" / "v1.yaml")

    with app.app_context():
        runner = EvaluationRunner(MockProvider())
        first_run = runner.run(dataset, prompt)
        second_run = runner.run(dataset, prompt)

        assert first_run.status == "completed"
        assert first_run.pass_rate == 1.0
        assert not any(result.cache_hit for result in first_run.results)

        assert second_run.status == "completed"
        assert second_run.mean_score == first_run.mean_score
        assert all(result.cache_hit for result in second_run.results)
