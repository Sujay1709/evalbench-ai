from flask import Blueprint, abort, render_template, request

from evalbench.comparisons import ComparisonError, compare_runs, paired_bootstrap
from evalbench.extensions import db
from evalbench.models import EvaluationRun
from evalbench.web.comparison import load_segments

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


def _comparison_runs():
    baseline = db.session.get(EvaluationRun, request.args.get("baseline", ""))
    candidate = db.session.get(EvaluationRun, request.args.get("candidate", ""))
    if baseline is None or candidate is None:
        abort(404)
    return baseline, candidate


@web_blueprint.get("/compare")
def comparison():
    runs = list(
        db.session.execute(
            db.select(EvaluationRun)
            .where(EvaluationRun.status == "completed")
            .order_by(EvaluationRun.created_at.desc())
        ).scalars()
    )
    context = dict(
        runs=runs,
        report=None,
        error=None,
        segments=None,
        intervals=None,
        advisory=None,
        segment_error=None,
    )
    if not request.args.get("baseline") and not request.args.get("candidate"):
        return render_template("comparison.html", **context)
    if not request.args.get("baseline") or not request.args.get("candidate"):
        context["error"] = "Select both a baseline and a candidate run."
        return render_template("comparison.html", **context), 400
    baseline, candidate = _comparison_runs()
    try:
        report = compare_runs(baseline, candidate)
    except ComparisonError as exc:
        context["error"] = str(exc)
        return render_template("comparison.html", **context), 400
    context.update(report=report, baseline=baseline, candidate=candidate)
    # Bound work on the public read-only endpoint. Larger analyses remain available in Python.
    if 2 <= len(report.examples) <= 1000:
        context["intervals"] = paired_bootstrap(report)
    else:
        context["advisory"] = (
            "Dashboard intervals require 2–1,000 pairs. Use the Python API for larger runs."
        )
    try:
        context["segments"] = load_segments(baseline, candidate)
    except (ValueError, OSError):
        context["segment_error"] = (
            "Tag and difficulty breakdowns unavailable. Restore the original dataset version "
            "in the local registry with the recorded content hash and split."
        )
    change = request.args.get("change", "all")
    if change not in {"all", "regressed", "improved", "unchanged"}:
        abort(400)
    context["pairs"] = [p for p in report.examples if change == "all" or p.change == change]
    return render_template("comparison.html", **context)


@web_blueprint.get("/compare/example")
def comparison_example():
    baseline, candidate = _comparison_runs()
    try:
        report = compare_runs(baseline, candidate)
    except ComparisonError as exc:
        return render_template("comparison_error.html", error=str(exc)), 400
    example_id = request.args.get("example", "")
    pair = next((p for p in report.examples if p.example_id == example_id), None)
    if pair is None:
        abort(404)
    before = next(r for r in baseline.results if r.example_id == example_id)
    after = next(r for r in candidate.results if r.example_id == example_id)
    return render_template(
        "comparison_example.html",
        baseline=baseline,
        candidate=candidate,
        pair=pair,
        before=before,
        after=after,
    )
