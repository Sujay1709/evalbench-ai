"""Request guards that hold for every route, including ones added later."""

from flask import Flask, jsonify, request

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def init_security(app: Flask) -> None:
    @app.before_request
    def reject_writes_in_read_only_demo():
        # Fails closed before routing, so a future write route cannot bypass demo mode.
        if app.config["DEMO_READ_ONLY"] and request.method not in SAFE_METHODS:
            return jsonify(error="read_only_demo", message="This public demo is read-only."), 403
        return None

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response
