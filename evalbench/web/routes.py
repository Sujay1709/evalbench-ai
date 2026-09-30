from pathlib import Path

from flask import Blueprint, abort, render_template, request

from evalbench.comparisons import ComparisonError, compare_runs, paired_bootstrap
from evalbench.comparisons.efficiency import build_leaderboards, summarize_efficiency
from evalbench.extensions import db
from evalbench.judges.calibration import (
    CalibrationError,
    build_calibration_report,
    load_calibration_cohort,
)
from evalbench.judges.rubrics import load_rubric
from evalbench.models import EvaluationRun
from evalbench.web.calibration import (
    eligible_calibration_runs,
    evidence_rows,
    selected_evidence,
)
from evalbench.web.comparison import load_segments

web_blueprint = Blueprint("web", __name__)
RUBRIC_PATH = Path(__file__).resolve().parents[2] / "rubrics" / "grounded_qa" / "v1.yaml"


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
    return render_template("run_detail.html", run=run, efficiency=summarize_efficiency(run))


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
    context["efficiencies"] = (summarize_efficiency(baseline), summarize_efficiency(candidate))
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


@web_blueprint.get("/leaderboard")
def leaderboard():
    runs = db.session.execute(db.select(EvaluationRun)).scalars().all()
    boards, excluded = build_leaderboards(runs)
    return render_template("leaderboard.html", boards=boards, excluded=excluded)


@web_blueprint.get("/calibration")
def calibration():
    """Render advisory judge-human agreement from an explicit evidence selection."""
    runs = eligible_calibration_runs()
    context = {
        "runs": runs,
        "run": None,
        "rows": (),
        "pair_count": 0,
        "partial_result_ids": (),
        "cohort": None,
        "report": None,
        "error": None,
    }
    run_id = request.args.get("run")
    if not run_id:
        return render_template("calibration.html", **context)

    run = next((candidate for candidate in runs if candidate.id == run_id), None)
    if run is None:
        abort(404)

    selections_by_result = {
        result.id: (
            request.args.get(f"judge-{result.id}") or None,
            request.args.get(f"human-{result.id}") or None,
        )
        for result in run.results
    }
    rows = evidence_rows(run, selections_by_result)
    selections, partial_result_ids = selected_evidence(rows)
    context.update(
        run=run,
        rows=rows,
        pair_count=len(selections),
        partial_result_ids=partial_result_ids,
    )
    if partial_result_ids:
        context["error"] = (
            "Choose both a completed judge attempt and a human label for every "
            "selected result before building a report."
        )
        return render_template("calibration.html", **context), 400
    if not selections:
        return render_template("calibration.html", **context)

    try:
        cohort = load_calibration_cohort(
            run.id,
            selections,
            rubric=load_rubric(RUBRIC_PATH),
        )
        context.update(
            cohort=cohort,
            report=build_calibration_report(cohort.pairs),
        )
    except CalibrationError as exc:
        context["error"] = str(exc)
        return render_template("calibration.html", **context), 400
    return render_template("calibration.html", **context)
