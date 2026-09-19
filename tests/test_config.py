import pytest
from pydantic import ValidationError
from sqlalchemy import text

from evalbench import create_app
from evalbench.config import Settings
from evalbench.extensions import db


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_postgres_urls_use_psycopg_with_bounded_pooling(scheme):
    settings = Settings(
        _env_file=None,
        database_url=f"{scheme}://user:p%40ss@localhost:5432/evalbench_test",
        database_pool_size=2,
        database_max_overflow=1,
    )
    config = settings.to_flask_config()
    url = config["SQLALCHEMY_DATABASE_URI"]
    options = config["SQLALCHEMY_ENGINE_OPTIONS"]

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss"
    assert options["pool_size"] == 2
    assert options["max_overflow"] == 1
    assert options["pool_pre_ping"] is True
    assert options["pool_timeout"] == 30
    assert options["pool_recycle"] == 300
    assert options["hide_parameters"] is True
    assert options["connect_args"] == {
        "sslmode": "disable",
        "connect_timeout": 10,
        "options": "-c timezone=UTC",
    }
    assert "p%40ss" not in repr(settings)


def test_sqlite_does_not_receive_postgres_pool_options():
    config = Settings(_env_file=None, database_url="sqlite:///:memory:").to_flask_config()

    assert config["SQLALCHEMY_DATABASE_URI"].drivername == "sqlite"
    assert config["SQLALCHEMY_ENGINE_OPTIONS"] == {"hide_parameters": True}


def test_sqlite_test_override_does_not_inherit_hosted_database_options(monkeypatch, tmp_path):
    cert = tmp_path / "database-ca.crt"
    cert.write_text("test certificate placeholder", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.example.supabase.co/postgres")
    monkeypatch.setenv("DATABASE_SSL_ROOT_CERT", str(cert))
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "DEMO_READ_ONLY": True,
        }
    )

    with app.app_context():
        assert db.engine.dialect.name == "sqlite"
        assert db.session.execute(text("SELECT 1")).scalar_one() == 1
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("host", ["db.example.supabase.co", "aws-0-region.pooler.supabase.com"])
def test_hosted_postgres_verifies_certificates_and_hostname(tmp_path, host):
    cert = tmp_path / "database-ca.crt"
    cert.write_text("test certificate placeholder", encoding="utf-8")
    config = Settings(
        _env_file=None,
        database_url=f"postgresql://user:secret@{host}:5432/postgres",
        database_ssl_root_cert=cert,
    ).to_flask_config()

    assert config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"] == {
        "sslmode": "verify-full",
        "sslrootcert": str(cert),
        "connect_timeout": 10,
        "options": "-c timezone=UTC",
    }


def test_supabase_url_certificate_options_are_normalized(tmp_path):
    cert = tmp_path / "database-ca.crt"
    cert.write_text("test certificate placeholder", encoding="utf-8")
    config = Settings(
        _env_file=None,
        database_url=f"postgresql://user:secret@db.example.supabase.co:5432/postgres"
        f"?sslmode=verify-full&sslrootcert={cert}",
    ).to_flask_config()

    assert config["SQLALCHEMY_DATABASE_URI"].query == {}
    assert config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["sslrootcert"] == str(cert)


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "require", "verify-ca"])
def test_hosted_postgres_rejects_weaker_tls(sslmode):
    with pytest.raises(ValidationError, match="sslmode=verify-full"):
        Settings(
            _env_file=None,
            database_url=f"postgresql://user:secret@db.example.supabase.co/postgres?sslmode={sslmode}",
        )


def test_hosted_postgres_requires_a_ca_file():
    with pytest.raises(ValidationError, match="DATABASE_SSL_ROOT_CERT"):
        Settings(
            _env_file=None, database_url="postgresql://user:secret@db.example.supabase.co/postgres"
        )


def test_production_loopback_cannot_disable_tls():
    with pytest.raises(ValidationError, match="sslmode=verify-full"):
        Settings(
            _env_file=None,
            app_env="production",
            database_url="postgresql://user:secret@localhost/postgres?sslmode=disable",
        )


@pytest.mark.parametrize(
    "query", ["host=remote.example", "service=remote", "sslmode=disable&sslmode=require"]
)
def test_query_overrides_cannot_bypass_tls_policy(query):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, database_url=f"postgresql://user:secret@localhost/postgres?{query}"
        )


def test_transaction_pooler_is_outside_this_slice():
    with pytest.raises(ValidationError, match="session-pooler"):
        Settings(
            _env_file=None, database_url="postgresql://user:secret@pooler.example:6543/postgres"
        )


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url-secret",
        "mysql://user:secret@localhost/db",
        "postgresql://user:secret@localhost:bad/db",
    ],
)
def test_configuration_errors_do_not_echo_database_credentials(url):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=url)

    assert url not in str(error.value)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("database_pool_size", 0),
        ("database_max_overflow", -1),
        ("database_connect_timeout_seconds", 0),
    ],
)
def test_database_resource_limits_are_validated(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_openai_provider_requires_an_api_key():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, llm_provider="openai", openai_api_key=None)


def test_openai_secret_is_not_copied_into_flask_config():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key="test-secret",
    )

    flask_config = settings.to_flask_config()

    assert flask_config["LLM_PROVIDER"] == "openai"
    assert flask_config["OPENAI_MODEL"] == "gpt-5.6-luna"
    assert "OPENAI_API_KEY" not in flask_config


def test_full_production_mode_requires_an_inngest_signing_key():
    with pytest.raises(ValidationError, match="INNGEST_SIGNING_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="production-secret",
            demo_read_only=False,
            inngest_signing_key=None,
        )


def test_read_only_production_demo_does_not_require_inngest_keys():
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="production-secret",
        demo_read_only=True,
        inngest_event_key=None,
        inngest_signing_key=None,
    )

    assert settings.demo_read_only is True


def test_inngest_secrets_are_not_copied_into_flask_config():
    settings = Settings(
        _env_file=None,
        inngest_event_key="event-secret",
        inngest_signing_key="signing-secret",
    )

    flask_config = settings.to_flask_config()

    assert flask_config["INNGEST_APP_ID"] == "evalbench"
    assert "INNGEST_EVENT_KEY" not in flask_config
    assert "INNGEST_SIGNING_KEY" not in flask_config
