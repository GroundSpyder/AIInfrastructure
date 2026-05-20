"""AI Fleet Dashboard — federates status from LilBlue, OBD, and Reaper.

The three per-service dashboards remain canonical for proxy routing and
metrics; this app polls each of their `/api/status` (and `/api/test`)
endpoints, forwarding the user's BirdMug-Auth cookie through so the
downstream auth layer keeps working unchanged.

Backend selector lives in the `?backend=` query param (`lilblue`/`obd`/
`reaper`). The browser-side tabs swap which value gets polled; the
backend never aggregates — it only routes one request at a time.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request

from flask import Flask, jsonify, make_response, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

from server.auth import require_auth
from server.bug_fairy import BugFairy
from server.html import INDEX_HTML

BACKENDS = {
    "lilblue": os.environ.get("LILBLUE_URL", "http://192.168.4.31:8792").rstrip("/"),
    "obd":     os.environ.get("OBD_URL",     "http://192.168.4.31:8791").rstrip("/"),
    "reaper":  os.environ.get("REAPER_URL",  "http://192.168.4.31:8793").rstrip("/"),
}

FEDERATION_TIMEOUT = int(os.environ.get("FEDERATION_TIMEOUT", "30"))

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
log = logging.getLogger(__name__)

_fairy.install_flask(app)


def _resolve_backend() -> tuple[str, str] | tuple[None, None]:
    """Return (backend_name, backend_url) from request.args['backend'].

    Returns (None, None) if the param is missing or unknown — caller should
    422 the request rather than guess a default."""
    name = (request.args.get("backend") or "").strip().lower()
    url = BACKENDS.get(name)
    if not url:
        return None, None
    return name, url


def _forward_auth_headers() -> dict[str, str]:
    """Copy the incoming user's auth credentials onto the outbound request.

    All three downstream dashboards share the same BIRDMUG_JWT_SECRET, so the
    cookie/bearer we received from the browser is also accepted by them.
    Cookies are the primary path (set domain-wide on .birdmug.com by
    accounts.birdmug.com); Authorization is a fallback for non-browser callers.
    """
    out: dict[str, str] = {"Accept": "application/json"}
    cookie_parts: list[str] = []
    for name in ("birdmug_token", "bm_token"):
        val = request.cookies.get(name)
        if val:
            cookie_parts.append(f"{name}={val}")
    if cookie_parts:
        out["Cookie"] = "; ".join(cookie_parts)
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        out["Authorization"] = auth_header
    return out


def _federate(method: str, backend_url: str, path: str, body: bytes | None = None) -> tuple[int, bytes, str]:
    """Make a single HTTP call to the downstream backend.

    Returns (status_code, body_bytes, content_type). Never raises — any
    exception is converted to a 502 response with a JSON error body, and
    Bug Fairy is notified for the inner cause so the failure surfaces.
    """
    req = urllib.request.Request(f"{backend_url}{path}", data=body, method=method)
    for key, val in _forward_auth_headers().items():
        req.add_header(key, val)
    if body is not None and method in ("POST", "PUT", "PATCH"):
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=FEDERATION_TIMEOUT) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as exc:
        # Backend returned a structured error — pass it through verbatim so
        # the browser sees the same JSON shape it would from the downstream.
        # Bug Fairy gets notified for >=500s only (4xx is usually auth/input
        # related and would just be noise); 4xx still passes through to the
        # browser so the user sees the real downstream message.
        body_out = exc.read()
        if exc.code >= 500:
            _fairy.capture_exception(exc)
        return exc.code, body_out, exc.headers.get("Content-Type", "application/json")
    except (TimeoutError, socket.timeout) as exc:
        _fairy.capture_exception(exc)
        return 504, json.dumps({"status": "down", "error": "upstream timeout", "detail": str(exc), "ts": time.time()}).encode("utf-8"), "application/json"
    except urllib.error.URLError as exc:
        # urllib wraps socket timeouts inside URLError on some Pythons.
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            _fairy.capture_exception(exc)
            return 504, json.dumps({"status": "down", "error": "upstream timeout", "detail": str(exc), "ts": time.time()}).encode("utf-8"), "application/json"
        _fairy.capture_exception(exc)
        return 502, json.dumps({"status": "down", "error": "upstream unreachable", "detail": str(exc), "ts": time.time()}).encode("utf-8"), "application/json"
    except Exception as exc:
        _fairy.capture_exception(exc)
        return 500, json.dumps({"status": "down", "error": str(exc), "ts": time.time()}).encode("utf-8"), "application/json"


@app.route("/")
@require_auth
def index():
    resp = make_response(INDEX_HTML)
    resp.content_type = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/fleet.png")
def favicon():
    return send_file("/app/fleet.png", mimetype="image/png")


@app.route("/api/status")
@require_auth
def api_status():
    name, url = _resolve_backend()
    if not name:
        return jsonify({"error": "unknown backend", "valid": list(BACKENDS)}), 422
    code, body, ctype = _federate("GET", url, "/api/status")
    resp = app.response_class(body, status=code, content_type=ctype)
    return resp


@app.route("/api/test", methods=["POST"])
@require_auth
def api_test():
    name, url = _resolve_backend()
    if not name:
        return jsonify({"error": "unknown backend", "valid": list(BACKENDS)}), 422
    code, body, ctype = _federate("POST", url, "/api/test", body=request.get_data())
    return app.response_class(body, status=code, content_type=ctype)


@app.route("/api/backends")
@require_auth
def api_backends():
    """Tiny endpoint the frontend uses to discover which backends are
    configured. Doesn't probe them — just returns the static set so the
    UI can render the right tabs."""
    return jsonify({"backends": list(BACKENDS)})


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8794"))
    app.run(host="0.0.0.0", port=port, debug=False)
