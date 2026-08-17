from pathlib import Path

from flask import Flask

from evalbench.config import Settings
from evalbench.extensions import db, migrate


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure an EvalBench Flask application."""
    settings = Settings()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(settings.to_flask_config())

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import models before migrations or create_all inspect SQLAlchemy metadata.
    from evalbench import models  # noqa: F401
    from evalbench.health import health_blueprint
    from evalbench.web import web_blueprint

    app.register_blueprint(health_blueprint)
    app.register_blueprint(web_blueprint)

    return app
