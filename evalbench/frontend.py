"""Opt-in, same-origin hosting for the built React frontend at /app/.

Jinja pages remain the default experience until the React views reach tested
parity, so this blueprint returns 404 unless FRONTEND_ENABLED is set.
"""

from pathlib import Path

from flask import Blueprint, abort, current_app, send_from_directory

frontend_blueprint = Blueprint("frontend", __name__, url_prefix="/app")


def _dist_directory() -> Path:
    if not current_app.config.get("FRONTEND_ENABLED"):
        abort(404)
    dist = Path(current_app.config["FRONTEND_DIST"])
    if not (dist / "index.html").is_file():
        abort(
            503,
            description=(
                "FRONTEND_ENABLED is set but no frontend build was found at "
                f"{dist}; run `npm ci && npm run build` in frontend/."
            ),
        )
    return dist


@frontend_blueprint.get("/", defaults={"path": ""})
@frontend_blueprint.get("/<path:path>")
def serve(path: str):
    dist = _dist_directory()
    if path and (dist / path).is_file():
        return send_from_directory(dist, path)
    # Client-side routes such as /app/runs/<id> resolve to the SPA entry point.
    return send_from_directory(dist, "index.html", max_age=0)
