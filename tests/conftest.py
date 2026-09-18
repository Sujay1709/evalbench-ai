import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from evalbench import create_app
from evalbench.config import Settings
from evalbench.database import LOCAL_DATABASE_HOSTS
from evalbench.extensions import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "SECRET_KEY": "test-secret",
        }
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def postgres_app():
    """Use only a disposable loopback database, with a unique schema per test."""
    raw_url = os.environ.get("EVALBENCH_TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("Set EVALBENCH_TEST_POSTGRES_URL to a local evalbench_test database")
    try:
        url = sa.engine.make_url(raw_url)
    except sa.exc.ArgumentError:
        pytest.fail("Invalid EVALBENCH_TEST_POSTGRES_URL", pytrace=False)
    if (
        url.host not in LOCAL_DATABASE_HOSTS
        or url.database != "evalbench_test"
        or url.query
        or url.drivername != "postgresql+psycopg"
    ):
        pytest.fail(
            "PostgreSQL tests require postgresql+psycopg, a loopback host, "
            "the evalbench_test database, and no query overrides",
            pytrace=False,
        )
    config = Settings(
        _env_file=None,
        app_env="testing",
        database_url=raw_url,
        llm_provider="mock",
        demo_read_only=True,
    ).to_flask_config()
    admin = sa.create_engine(url, **config["SQLALCHEMY_ENGINE_OPTIONS"])
    schema = f"evalbench_test_{uuid4().hex}"
    app = None
    try:
        with admin.begin() as connection:
            connection.execute(sa.schema.CreateSchema(schema))
        options = config["SQLALCHEMY_ENGINE_OPTIONS"]
        options["connect_args"] = {
            **options["connect_args"],
            "options": f"-csearch_path={schema} -c timezone=UTC",
        }
        app = create_app({**config, "TESTING": True, "SECRET_KEY": "test-secret"})
        yield app
    finally:
        if app is not None:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()
        # The generated schema is the only destructive target; never drop public.
        with admin.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True, if_exists=True))
        admin.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_app(request, tmp_path):
    if request.param == "postgresql":
        yield request.getfixturevalue("postgres_app")
        return
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'migration.db'}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"hide_parameters": True},
            "SECRET_KEY": "test-secret",
        }
    )
    try:
        yield app
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
