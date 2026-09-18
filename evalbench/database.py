"""Database connection policy shared by Flask and its migration commands."""

from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1"}


def database_config(
    database_url: str,
    *,
    production: bool,
    ssl_root_cert: Path | None,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    pool_recycle: int,
    connect_timeout: int,
) -> dict:
    """Normalize PostgreSQL URLs and fail closed on insecure hosted connections."""
    try:
        url = make_url(database_url)
        # Accessing port also validates malformed/non-numeric ports.
        port = url.port
    except (ArgumentError, ValueError):
        raise ValueError("Invalid DATABASE_URL; use a SQLite or PostgreSQL URL") from None

    if url.drivername in {"sqlite", "sqlite+pysqlite"}:
        return {
            "SQLALCHEMY_DATABASE_URI": url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"hide_parameters": True},
        }
    if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("DATABASE_URL must use SQLite or PostgreSQL with the psycopg driver")
    if not url.host or not url.database or not url.username:
        raise ValueError("PostgreSQL DATABASE_URL requires a host, database, and username")
    # Query-level host/service overrides could bypass the loopback-only TLS exception.
    if set(url.query) - {"sslmode", "sslrootcert"}:
        raise ValueError(
            "PostgreSQL URL supports only sslmode/sslrootcert query options; "
            "configure pooling and timeouts with DATABASE_* variables"
        )

    requires_tls = production or url.host not in LOCAL_DATABASE_HOSTS
    sslmode = url.query.get("sslmode", "verify-full" if requires_tls else "disable")
    if not isinstance(sslmode, str) or sslmode not in {"disable", "verify-full"}:
        raise ValueError("Use sslmode=verify-full; sslmode=disable is only for local development")
    if requires_tls and sslmode != "verify-full":
        raise ValueError("Hosted/production PostgreSQL requires sslmode=verify-full")
    if requires_tls and port == 6543:
        raise ValueError(
            "Use a direct or session-pooler PostgreSQL connection (port 5432), "
            "not the transaction pooler, for this integration"
        )

    cert = ssl_root_cert or url.query.get("sslrootcert")
    connect_args = {
        "sslmode": sslmode,
        "connect_timeout": connect_timeout,
        "options": "-c timezone=UTC",
    }
    if sslmode == "verify-full":
        if not isinstance(cert, (str, Path)) or not Path(cert).is_file():
            raise ValueError(
                "Certificate-verified PostgreSQL requires DATABASE_SSL_ROOT_CERT "
                "pointing to a readable CA certificate file"
            )
        connect_args["sslrootcert"] = str(cert)

    return {
        "SQLALCHEMY_DATABASE_URI": url.set(drivername="postgresql+psycopg", query={}),
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "connect_args": connect_args,
            "pool_pre_ping": True,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
            "hide_parameters": True,
        },
    }
