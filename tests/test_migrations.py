import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from evalbench import create_app
from evalbench.extensions import db
from tests.conftest import PROJECT_ROOT


def test_run_metadata_migrations_backfill_and_require_new_fields(tmp_path):
    database_path = tmp_path / "migration.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "SECRET_KEY": "test-secret",
        }
    )
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

        command.upgrade(config, "head")

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
