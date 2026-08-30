import inngest
import inngest.flask
from flask import Flask
from pydantic import SecretStr

from evalbench.config import Settings
from evalbench.workflows.functions import create_workflow_functions


def _secret_value(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    return secret.get_secret_value()


def init_inngest(app: Flask, settings: Settings) -> inngest.Inngest | None:
    """Register EvalBench workflows unless the app is a read-only public demo."""

    if app.config["DEMO_READ_ONLY"]:
        return None

    is_production = app.config["APP_ENV"] == "production"
    client = inngest.Inngest(
        app_id=settings.inngest_app_id,
        event_key=_secret_value(settings.inngest_event_key),
        signing_key=_secret_value(settings.inngest_signing_key),
        is_production=is_production,
    )
    functions = create_workflow_functions(client, app)

    inngest.flask.serve(
        app,
        client,
        functions,
        enable_unauthed_sync=not is_production,
        serve_path="/api/inngest",
    )
    app.extensions["inngest"] = client
    app.extensions["inngest_functions"] = functions
    return client
