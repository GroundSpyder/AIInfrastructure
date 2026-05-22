"""AI Fleet Dashboard backend.

Serves:
  - /            outer tabbed shell (REAPER | LILBLUE | OBD | MODELS)
  - /models      fleet-level model-management page (used by MODELS tab)
  - /api/...     model-management endpoints (see server/models_api.py)
  - /health      watchdog + Kuma probe
  - /fleet.png   favicon

The three per-service tabs are loaded into iframes pointing at the real
public URLs (https://{reaper,lilblue,obd}.birdmug.com/) so each renders
with its original full chrome. This backend owns the MODELS tab and the
fleet-level model CRUD that drives it.

See server/fleet_ssh.py for the SSH-based control plane to MB and
Kaydanski (Kyle's directive: SSH over per-host Flask agents, since the
agents die silently).
"""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, make_response, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

from server.auth import require_auth
from server.bug_fairy import BugFairy
from server.html import INDEX_HTML
from server.models_api import bp as models_bp
from server.models_html import MODELS_HTML

_fairy = BugFairy(
    api_key=os.environ.get("BUG_FAIRY_API_KEY", ""),
    app="ai-fleet-dashboard",
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

_fairy.install_flask(app)
app.register_blueprint(models_bp)


@app.route("/")
@require_auth
def index():
    resp = make_response(INDEX_HTML)
    resp.content_type = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/models")
@require_auth
def models_page():
    resp = make_response(MODELS_HTML)
    resp.content_type = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/fleet.png")
def favicon():
    return send_file("/app/fleet.png", mimetype="image/png")


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8794"))
    app.run(host="0.0.0.0", port=port, debug=False)
