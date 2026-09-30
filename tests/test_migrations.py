import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from evalbench.extensions import db
from tests.conftest import PROJECT_ROOT


def test_run_metadata_migrations_backfill_and_require_new_fields(migration_app):
    app = migration_app
    config = Config(str(PROJECT_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))

    with app.app_context():
        command.upgrade(config, "aab0bf3b7b5b")
        with db.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO evaluation_runs (
                        id, dataset_name, dataset_version, dataset_hash,
                        prompt_id, prompt_version, provider, status,
                        total_examples, passed_examples, mean_score, created_at
                    ) VALUES (
                        'legacy-run', 'automotive_qa', 'v1', :dataset_hash,
                        'automotive-qa', 'v1', 'mock', 'completed',
                        5, 5, 1.0, '2026-08-17 00:00:00'
                    )
                    """
                ),
                {"dataset_hash": "a" * 64},
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO evaluation_runs (
                        id, dataset_name, dataset_version, dataset_hash,
                        prompt_id, prompt_version, provider, status,
                        total_examples, passed_examples, mean_score,
                        error_message, created_at
                    ) VALUES (
                        'legacy-failed-run', 'automotive_qa', 'v1', :dataset_hash,
                        'automotive-qa', 'v1', 'mock', 'failed',
                        5, 0, 0.0, 'legacy failure', '2026-08-17 00:00:00'
                    )
                    """
                ),
                {"dataset_hash": "d" * 64},
            )

        with db.engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO example_results (
                        run_id, example_id, input_json, output_text, passed,
                        score, scorer_details, cache_hit, latency_ms
                    ) VALUES (
                        'legacy-run', 'old-example', '{}', 'old output', :passed,
                        1, '[]', :cache_hit, 12
                    )
                    """
                ),
                {"passed": True, "cache_hit": False},
            )
            connection.execute(
                sa.text(
                    """
                    INSERT INTO example_results (
                        run_id, example_id, input_json, output_text, passed,
                        score, scorer_details, cache_hit, latency_ms
                    ) VALUES (
                        'legacy-run', 'old-example-2', '{}', 'candidate B', :passed,
                        1, '[]', :cache_hit, 14
                    )
                    """
                ),
                {"passed": True, "cache_hit": False},
            )

        command.upgrade(config, "head")

        with db.engine.connect() as connection:
            historical_usage = connection.execute(
                sa.text("SELECT usage_json FROM example_results WHERE example_id = 'old-example'")
            ).scalar_one()
        assert historical_usage is None
        assert sa.inspect(db.engine).has_table("judge_attempts")
        assert sa.inspect(db.engine).has_table("human_label_sets")
        assert sa.inspect(db.engine).has_table("kev_decision_attempts")
        assert sa.inspect(db.engine).has_table("pairwise_judge_attempts")
        judge_columns = {
            column["name"]: column for column in sa.inspect(db.engine).get_columns("judge_attempts")
        }
        assert not judge_columns["result_id"]["nullable"]
        assert not judge_columns["request_text"]["nullable"]
        assert not judge_columns["status"]["nullable"]
        label_columns = {
            column["name"]: column
            for column in sa.inspect(db.engine).get_columns("human_label_sets")
        }
        assert not label_columns["result_id"]["nullable"]
        assert not label_columns["ratings_json"]["nullable"]
        kev_columns = {
            column["name"]: column
            for column in sa.inspect(db.engine).get_columns("kev_decision_attempts")
        }
        assert not kev_columns["result_id"]["nullable"]
        assert not kev_columns["request_json"]["nullable"]
        pairwise_columns = {
            column["name"]: column
            for column in sa.inspect(db.engine).get_columns("pairwise_judge_attempts")
        }
        assert not pairwise_columns["comparison_id"]["nullable"]
        assert not pairwise_columns["dataset_split"]["nullable"]
        assert not pairwise_columns["presentation_order"]["nullable"]
        assert not pairwise_columns["request_text"]["nullable"]
        command.check(config)

        with db.engine.connect() as connection:
            result_ids = connection.execute(
                sa.text(
                    "SELECT id FROM example_results WHERE run_id = 'legacy-run' "
                    "ORDER BY id"
                )
            ).scalars().all()
        assert len(result_ids) == 2
        with pytest.raises(sa.exc.IntegrityError, match="ck_pairwise_split"):
            with db.engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO pairwise_judge_attempts (
                            id, comparison_id, result_a_id, result_b_id,
                            dataset_split, presentation_order, rubric_id,
                            rubric_version, rubric_hash, prompt_version,
                            prompt_template_hash, request_hash, request_text,
                            judge_model, status, created_at
                        ) VALUES (
                            'pairwise-invalid-split', 'pairwise-comparison',
                            :result_a, :result_b, 'legacy_mixed', 'ab',
                            'grounded_qa', 'v1', :rubric_hash, 'v1',
                            :prompt_hash, :request_hash, '{}', 'test-model',
                            'completed', '2026-09-29 00:00:00'
                        )
                        """
                    ),
                    {
                        "result_a": result_ids[0],
                        "result_b": result_ids[1],
                        "rubric_hash": "a" * 64,
                        "prompt_hash": "b" * 64,
                        "request_hash": "c" * 64,
                    },
                )

        with db.engine.connect() as connection:
            migrated_run = connection.execute(
                sa.text(
                    "SELECT dataset_split, correlation_id, error_category "
                    "FROM evaluation_runs WHERE id = 'legacy-run'"
                )
            ).one()
            migrated_failed_run = connection.execute(
                sa.text(
                    "SELECT dataset_split, correlation_id, error_category "
                    "FROM evaluation_runs WHERE id = 'legacy-failed-run'"
                )
            ).one()

        with pytest.raises(sa.exc.IntegrityError, match="dataset_split"):
            with db.engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO evaluation_runs (
                            id, correlation_id, dataset_name, dataset_version, dataset_hash,
                            prompt_id, prompt_version, provider, status,
                            total_examples, passed_examples, mean_score, created_at
                        ) VALUES (
                            'missing-split-run', 'missing-split-correlation',
                            'automotive_qa', 'v1', :dataset_hash,
                            'automotive-qa', 'v1', 'mock', 'completed',
                            5, 5, 1.0, '2026-08-24 00:00:00'
                        )
                        """
                    ),
                    {"dataset_hash": "b" * 64},
                )

        with pytest.raises(sa.exc.IntegrityError, match="correlation_id"):
            with db.engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO evaluation_runs (
                            id, dataset_name, dataset_version, dataset_hash,
                            dataset_split, prompt_id, prompt_version, provider, status,
                            total_examples, passed_examples, mean_score, created_at
                        ) VALUES (
                            'missing-correlation-run', 'automotive_qa', 'v1', :dataset_hash,
                            'development', 'automotive-qa', 'v1', 'mock', 'completed',
                            5, 5, 1.0, '2026-08-29 00:00:00'
                        )
                        """
                    ),
                    {"dataset_hash": "c" * 64},
                )

    assert migrated_run.dataset_split == "legacy_mixed"
    assert migrated_run.correlation_id == "legacy-run"
    assert migrated_run.error_category is None
    assert migrated_failed_run.dataset_split == "legacy_mixed"
    assert migrated_failed_run.correlation_id == "legacy-failed-run"
    assert migrated_failed_run.error_category == "legacy_unclassified"
