from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from evalbench.demo import demo_ready
from evalbench.extensions import db

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def liveness():
    return jsonify(status="ok"), 200


@health_blueprint.get("/health/ready")
def readiness():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="not_ready", checks={"database": "failed"}), 503

    checks = {"database": "ok"}
    if current_app.config["DEMO_READ_ONLY"]:
        try:
            seeded = demo_ready()
        except Exception:
            seeded = False
        checks["demo_data"] = "ok" if seeded else "missing"
        if not seeded:
            return jsonify(status="not_ready", checks=checks), 503

    return jsonify(status="ready", checks=checks), 200
