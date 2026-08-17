from flask import Blueprint, jsonify
from sqlalchemy import text

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

    return jsonify(status="ready", checks={"database": "ok"}), 200
