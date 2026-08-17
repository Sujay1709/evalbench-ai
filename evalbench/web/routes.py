from flask import Blueprint, abort, render_template

from evalbench.extensions import db
from evalbench.models import EvaluationRun

web_blueprint = Blueprint("web", __name__)


@web_blueprint.get("/")
def index():
    runs = db.session.execute(
        db.select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(8)
    ).scalars()
    return render_template("index.html", runs=list(runs))


@web_blueprint.get("/runs/<run_id>")
def run_detail(run_id: str):
    run = db.session.get(EvaluationRun, run_id)
    if run is None:
        abort(404)
    return render_template("run_detail.html", run=run)
