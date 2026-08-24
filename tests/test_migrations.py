import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from evalbench import create_app
from evalbench.extensions import db
from tests.conftest import PROJECT_ROOT


def test_dataset_split_migration_labels_historical_runs(tmp_path):
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

        command.upgrade(config, "head")

        with db.engine.connect() as connection:
            split = connection.execute(
                sa.text(
                    "SELECT dataset_split FROM evaluation_runs WHERE id = 'legacy-run'"
                )
            ).scalar_one()

        with pytest.raises(sa.exc.IntegrityError, match="dataset_split"):
            with db.engine.begin() as connection:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO evaluation_runs (
                            id, dataset_name, dataset_version, dataset_hash,
                            prompt_id, prompt_version, provider, status,
                            total_examples, passed_examples, mean_score, created_at
                        ) VALUES (
                            'missing-split-run', 'automotive_qa', 'v1', :dataset_hash,
                            'automotive-qa', 'v1', 'mock', 'completed',
                            5, 5, 1.0, '2026-08-24 00:00:00'
                        )
                        """
                    ),
                    {"dataset_hash": "b" * 64},
                )

    assert split == "legacy_mixed"
