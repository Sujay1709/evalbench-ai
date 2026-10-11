from flask import Blueprint, jsonify, request

from evalbench.api.schemas import ApiError, RunList, run_detail, run_summary
from evalbench.comparisons.efficiency import summarize_efficiency
from evalbench.extensions import db
from evalbench.models import EvaluationRun

api_blueprint = Blueprint("api", __name__, url_prefix="/api/v1")

DEFAULT_RUN_LIMIT = 50
MAX_RUN_LIMIT = 200


def _error(message: str, status: int):
    return jsonify(ApiError(error=message).model_dump(mode="json")), status


@api_blueprint.get("/runs")
def list_runs():
    raw_limit = request.args.get("limit", str(DEFAULT_RUN_LIMIT))
    if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= MAX_RUN_LIMIT:
        return _error(f"limit must be an integer from 1 to {MAX_RUN_LIMIT}", 400)

    runs = db.session.execute(
        db.select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(int(raw_limit))
    ).scalars()
    payload = RunList(runs=tuple(run_summary(run) for run in runs))
    return jsonify(payload.model_dump(mode="json"))


@api_blueprint.get("/runs/<run_id>")
def get_run(run_id: str):
    run = db.session.get(EvaluationRun, run_id)
    if run is None:
        return _error(f"Evaluation run '{run_id}' was not found", 404)
    return jsonify(run_detail(run, summarize_efficiency(run)).model_dump(mode="json"))
