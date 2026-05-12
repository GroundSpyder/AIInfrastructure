from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from flask import Flask, jsonify, make_response, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix

from server.auth import require_auth
from server.bug_fairy import BugFairy
from server.html import INDEX_HTML
from server import lilblue
from server.tracker import tracker

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://kaydanskipc:11434").rstrip("/")

_fairy = BugFairy(
    api_key=os.environ.get("BUG_FAIRY_API_KEY", ""),
    app="lilblue-dashboard",
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


@app.route("/lilblue.png")
def favicon():
    return send_file("/app/lilblue.png", mimetype="image/png")


@app.route("/api/status")
@require_auth
def api_status():
    try:
        payload = lilblue.status_payload()
        status_code = 503 if payload.get("status") == "down" else 200
        return jsonify(payload), status_code
    except Exception as exc:
        _fairy.capture_exception(exc)
        return jsonify({"status": "down", "error": str(exc), "ts": time.time()}), 503


@app.route("/api/test", methods=["POST"])
@require_auth
def api_test():
    try:
        return jsonify(lilblue.health_test())
    except Exception as exc:
        _fairy.capture_exception(exc)
        return jsonify({"ok": False, "failed": 1, "checks": [], "error": str(exc), "ts": time.time()}), 500


@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    started = time.time()
    body = request.get_data()
    try:
        req_data = json.loads(body) if body else {}
    except Exception:
        req_data = {}
    model = req_data.get("model", "")
    is_stream = req_data.get("stream", False)

    tracker.start("POST", "/v1/chat/completions", model)

    fwd = urllib.request.Request(
        f"{OLLAMA_URL}/v1/chat/completions",
        data=body,
        method="POST",
    )
    fwd.add_header("Content-Type", "application/json")
    fwd.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(fwd, timeout=300) as resp:
            status_code = resp.status
            if is_stream:
                def _stream(response=resp):
                    try:
                        while True:
                            chunk = response.read(4096)
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        duration_ms = int((time.time() - started) * 1000)
                        tracker.finish(status_code, duration_ms, model=model)
                return app.response_class(
                    _stream(), status=status_code,
                    content_type=resp.headers.get("Content-Type", "text/event-stream"),
                    direct_passthrough=True,
                )
            else:
                data = resp.read()
                duration_ms = int((time.time() - started) * 1000)
                generation = _parse_generation(data, duration_ms)
                tracker.finish(status_code, duration_ms, model=model, generation=generation)
                return app.response_class(data, status=status_code, content_type="application/json")
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.time() - started) * 1000)
        err_body = exc.read()
        tracker.finish(exc.code, duration_ms, model=model)
        return app.response_class(err_body, status=exc.code, content_type="application/json")
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(500, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/v1/models")
def proxy_models():
    fwd = urllib.request.Request(f"{OLLAMA_URL}/v1/models", method="GET")
    fwd.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(fwd, timeout=10) as resp:
            return app.response_class(resp.read(), status=resp.status, content_type="application/json")
    except urllib.error.HTTPError as exc:
        return app.response_class(exc.read(), status=exc.code, content_type="application/json")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


def _parse_generation(data: bytes, duration_ms: int) -> dict | None:
    try:
        parsed = json.loads(data)
        usage = parsed.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        if not completion_tokens:
            return None
        seconds = duration_ms / 1000
        gen_tps = round(completion_tokens / seconds, 2) if seconds > 0 else 0
        prompt_tps = round(prompt_tokens / seconds, 2) if seconds > 0 else 0
        return {
            "generated_tokens": completion_tokens,
            "seconds": round(seconds, 2),
            "generate_tps": gen_tps,
            "prompt_tps": prompt_tps,
            "context": prompt_tokens + completion_tokens,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("_parse_generation failed: %s", exc)
        return None


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8792"))
    app.run(host="0.0.0.0", port=port, debug=False)
