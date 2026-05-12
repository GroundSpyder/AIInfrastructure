from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from flask import Flask, jsonify, make_response, request
from werkzeug.middleware.proxy_fix import ProxyFix

from server.auth import require_auth
from server.bug_fairy import BugFairy
from server.html import INDEX_HTML
from server import orthos

ROOT = Path(__file__).resolve().parent.parent

_fairy = BugFairy(
    api_key=os.environ.get("BUG_FAIRY_API_KEY", ""),
    app="obd",
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

_fairy.install_flask(app)


@app.route("/")
@require_auth
def index():
    resp = make_response(INDEX_HTML)
    resp.content_type = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/favicon.ico")
def favicon():
    icon_path = ROOT / "favicon.ico"
    if icon_path.exists():
        resp = make_response(icon_path.read_bytes())
        resp.content_type = "image/x-icon"
        return resp
    return jsonify({"error": "not found"}), 404


@app.route("/api/status")
@require_auth
def api_status():
    try:
        payload = orthos.status_payload()
        status_code = 503 if payload.get("status") == "down" else 200
        return jsonify(payload), status_code
    except Exception as exc:
        _fairy.capture_exception(exc)
        return jsonify({"status": "down", "error": str(exc), "ts": time.time()}), 503


@app.route("/api/test", methods=["POST"])
@require_auth
def api_test():
    try:
        return jsonify(orthos.health_test())
    except Exception as exc:
        _fairy.capture_exception(exc)
        return jsonify({"ok": False, "failed": 1, "checks": [], "error": str(exc), "ts": time.time()})


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8791"))
    app.run(host="0.0.0.0", port=port, debug=False)
