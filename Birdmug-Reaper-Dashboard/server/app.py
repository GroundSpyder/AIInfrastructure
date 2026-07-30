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
from server.bug_fairy import BugFairy, mark_expected
from server.html import INDEX_HTML
from server import reaper
from server.tracker import tracker

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.4.33:11434").rstrip("/")
# Match Kyle-Rag's KYLE_RAG_OLLAMA_TIMEOUT_SECONDS. When the client times out at
# 30s, we shouldn't keep an upstream connection open longer — that piles dead
# work onto Ollama and prevents the queue from draining.
PROXY_EMBED_TIMEOUT = int(os.environ.get("PROXY_EMBED_TIMEOUT", "30"))
PROXY_GEN_TIMEOUT = int(os.environ.get("PROXY_GEN_TIMEOUT", "300"))

_fairy = BugFairy(
    api_key=os.environ.get("BUG_FAIRY_API_KEY", ""),
    app="reaper-dashboard",
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

_fairy.install_flask(app)

_log = logging.getLogger(__name__)

# Single definition lives in server.reaper so the API client and the HTTP layer
# cannot drift on what "away" means.
_is_node_away = reaper.is_node_away


def _away_payload(detail: str) -> dict:
    return {
        "error": "reaper node is away",
        "away": True,
        "detail": detail,
        "hint": reaper.AWAY_HINT,
    }


def _handle_away(exc, token, duration_ms, model):
    """Shared response for "Master Blaster is not accepting connections".

    Answers honestly with a 503 so the LiteLLM gateway cools this backend down
    and fails over, but does not file a Bug Fairy report - see reaper.is_node_away
    for why an expected absence must not use the error channel.

    Only suppresses while the gate agrees this is a deliberate pause AND the
    absence is inside the expected-gaming budget. Past that, status_payload()
    reports "down" and we let it through to Bug Fairy like any other fault.
    """
    tracker.finish(token, 503, duration_ms, model=model)
    gate = reaper.get_gate_report()
    expected = bool(gate and gate.get("state") == "paused")
    if expected:
        _log.info("reaper node away (gate confirms pause): %s", exc)
        mark_expected("master blaster gated for gaming")
    else:
        # Unreachable with no gate confirmation is NOT expected. Report it.
        _log.warning("reaper node unreachable with no gate confirmation: %s", exc)
        _fairy.capture_exception(exc)
    return jsonify(_away_payload(str(exc))), 503


@app.route("/")
@require_auth
def index():
    resp = make_response(INDEX_HTML)
    resp.content_type = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/reaper.png")
def favicon():
    return send_file("/app/reaper.png", mimetype="image/png")


@app.route("/api/status")
@require_auth
def api_status():
    try:
        payload = reaper.status_payload()
        # "away" returns 200: this dashboard is working perfectly, it is just
        # reporting that a remote node is deliberately offline. Returning 503
        # here claimed the dashboard itself was broken and generated 1,688
        # bogus reports for GET /api/status alone.
        status_code = 503 if payload.get("status") == "down" else 200
        return jsonify(payload), status_code
    except Exception as exc:
        if reaper.is_node_away(exc):
            return jsonify({
                "status": "away",
                "error": str(exc),
                "hint": reaper.AWAY_HINT,
                "ts": time.time(),
            }), 200
        _fairy.capture_exception(exc)
        return jsonify({"status": "down", "error": str(exc), "ts": time.time()}), 503


@app.route("/api/test", methods=["POST"])
@require_auth
def api_test():
    try:
        return jsonify(reaper.health_test())
    except Exception as exc:
        _fairy.capture_exception(exc)
        return jsonify({"ok": False, "failed": 1, "checks": [], "error": str(exc), "ts": time.time()}), 500


@app.route("/v1/chat/completions", methods=["POST"])
def proxy_chat():
    started = time.time()
    body = request.get_data()
    try:
        req_data = json.loads(body) if body else {}
    except Exception as exc:
        # Do not swallow this. An unparseable body means the model attribution
        # below silently becomes "", mis-attributing the request in the tracker
        # and the performance panel. The sibling proxy routes already warn here;
        # this one dropped it entirely.
        req_data = {}
        _log.warning("proxy_chat: failed to parse JSON body (%d bytes): %s", len(body), exc)
    model = req_data.get("model", "")
    is_stream = req_data.get("stream", False)

    token = tracker.start("POST", "/v1/chat/completions", model)

    fwd = urllib.request.Request(
        f"{OLLAMA_URL}/v1/chat/completions",
        data=body,
        method="POST",
    )
    fwd.add_header("Content-Type", "application/json")
    fwd.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(fwd, timeout=PROXY_GEN_TIMEOUT) as resp:
            status_code = resp.status
            if is_stream:
                def _stream(response=resp):
                    final_status = status_code
                    try:
                        while True:
                            try:
                                chunk = response.read(4096)
                            except Exception as exc:
                                final_status = 502
                                _fairy.capture_exception(exc)
                                break
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        duration_ms = int((time.time() - started) * 1000)
                        tracker.finish(token, final_status, duration_ms, model=model)
                return app.response_class(
                    _stream(), status=status_code,
                    content_type=resp.headers.get("Content-Type", "text/event-stream"),
                    direct_passthrough=True,
                )
            else:
                data = resp.read()
                duration_ms = int((time.time() - started) * 1000)
                generation = _parse_generation(data, duration_ms)
                tracker.finish(token, status_code, duration_ms, model=model, generation=generation)
                return app.response_class(data, status=status_code, content_type="application/json")
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.time() - started) * 1000)
        err_body = exc.read()
        tracker.finish(token, exc.code, duration_ms, model=model)
        return app.response_class(err_body, status=exc.code, content_type="application/json")
    except (TimeoutError, socket.timeout) as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 504, duration_ms, model=model)
        return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
    except urllib.error.URLError as exc:
        # Wraps TimeoutError when timeout expires inside urlopen
        duration_ms = int((time.time() - started) * 1000)
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            tracker.finish(token, 504, duration_ms, model=model)
            return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
        if _is_node_away(exc):
            return _handle_away(exc, token, duration_ms, model)
        tracker.finish(token, 502, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": "upstream unreachable", "detail": str(exc)}), 502
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 500, duration_ms, model=model)
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
        if _is_node_away(exc):
            gate = reaper.get_gate_report()
            if gate and gate.get("state") == "paused":
                _log.info("reaper node away on /v1/models: %s", exc)
                mark_expected("master blaster gated for gaming")
                return jsonify(_away_payload(str(exc))), 503
            _log.warning("reaper unreachable on /v1/models, no gate confirmation: %s", exc)
        _fairy.capture_exception(exc)
        return jsonify({"error": str(exc)}), 503


@app.route("/api/generate", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def proxy_ollama_generate():
    path = request.path
    started = time.time()
    body = request.get_data()
    try:
        req_data = json.loads(body) if body else {}
    except Exception:
        req_data = {}
    if not req_data and body:
        logging.getLogger(__name__).warning("proxy_ollama_generate: failed to parse JSON body (%d bytes)", len(body))
    model = req_data.get("model", "")
    # Ollama defaults stream=true; respect what the client sends
    is_stream = req_data.get("stream", True)

    token = tracker.start("POST", path, model)

    fwd = urllib.request.Request(f"{OLLAMA_URL}{path}", data=body, method="POST")
    fwd.add_header("Content-Type", "application/json")
    fwd.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(fwd, timeout=PROXY_GEN_TIMEOUT) as resp:
            status_code = resp.status
            if is_stream:
                def _stream(response=resp):
                    final_status = status_code
                    try:
                        while True:
                            try:
                                chunk = response.read(4096)
                            except Exception as exc:
                                final_status = 502
                                _fairy.capture_exception(exc)
                                break
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        duration_ms = int((time.time() - started) * 1000)
                        tracker.finish(token, final_status, duration_ms, model=model)
                return app.response_class(
                    _stream(), status=status_code,
                    content_type=resp.headers.get("Content-Type", "application/x-ndjson"),
                    direct_passthrough=True,
                )
            else:
                data = resp.read()
                duration_ms = int((time.time() - started) * 1000)
                generation = _parse_generation_native(data, duration_ms)
                tracker.finish(token, status_code, duration_ms, model=model, generation=generation)
                return app.response_class(data, status=status_code, content_type="application/json")
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.time() - started) * 1000)
        err_body = exc.read()
        tracker.finish(token, exc.code, duration_ms, model=model)
        return app.response_class(err_body, status=exc.code, content_type="application/json")
    except (TimeoutError, socket.timeout) as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 504, duration_ms, model=model)
        return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
    except urllib.error.URLError as exc:
        duration_ms = int((time.time() - started) * 1000)
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            tracker.finish(token, 504, duration_ms, model=model)
            return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
        if _is_node_away(exc):
            return _handle_away(exc, token, duration_ms, model)
        tracker.finish(token, 502, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": "upstream unreachable", "detail": str(exc)}), 502
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 500, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/embed", methods=["POST"])
@app.route("/api/embeddings", methods=["POST"])
def proxy_ollama_embed():
    path = request.path
    started = time.time()
    body = request.get_data()
    try:
        req_data = json.loads(body) if body else {}
    except Exception:
        req_data = {}
    if not req_data and body:
        logging.getLogger(__name__).warning("proxy_ollama_embed: failed to parse JSON body (%d bytes)", len(body))
    model = req_data.get("model", "")

    token = tracker.start("POST", path, model)

    fwd = urllib.request.Request(f"{OLLAMA_URL}{path}", data=body, method="POST")
    fwd.add_header("Content-Type", "application/json")
    fwd.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(fwd, timeout=PROXY_EMBED_TIMEOUT) as resp:
            status_code = resp.status
            data = resp.read()
            duration_ms = int((time.time() - started) * 1000)
            generation = _parse_embed_stats(data, duration_ms)
            tracker.finish(token, status_code, duration_ms, model=model, generation=generation)
            return app.response_class(data, status=status_code, content_type="application/json")
    except urllib.error.HTTPError as exc:
        duration_ms = int((time.time() - started) * 1000)
        err_body = exc.read()
        tracker.finish(token, exc.code, duration_ms, model=model)
        return app.response_class(err_body, status=exc.code, content_type="application/json")
    except (TimeoutError, socket.timeout) as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 504, duration_ms, model=model)
        return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
    except urllib.error.URLError as exc:
        duration_ms = int((time.time() - started) * 1000)
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            tracker.finish(token, 504, duration_ms, model=model)
            return jsonify({"error": "upstream timeout", "detail": str(exc)}), 504
        if _is_node_away(exc):
            return _handle_away(exc, token, duration_ms, model)
        tracker.finish(token, 502, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": "upstream unreachable", "detail": str(exc)}), 502
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        tracker.finish(token, 500, duration_ms, model=model)
        _fairy.capture_exception(exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/gate", methods=["POST"])
def api_gate():
    """Receive a gate heartbeat from Master Blaster's Game-Watch watcher.

    Unauthenticated for the same reason the proxy routes are: this port is bound
    LAN-only and the watcher runs as SYSTEM with no BirdMug-Auth token. The
    payload carries no secrets and the worst a LAN actor can do is make the
    dashboard say "away" - it cannot start, stop, or route anything.
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}
    state = str(payload.get("state", ""))
    if state not in ("available", "paused"):
        return jsonify({"error": "state must be 'available' or 'paused'"}), 400
    entry = reaper.record_gate_state(payload)
    _log.info("gate heartbeat: state=%s owner=%s game=%s",
              entry["state"], entry["owner"], entry["game"])
    return jsonify({"ok": True, "recorded": entry}), 200


@app.route("/api/node-health")
def api_node_health():
    """Unauthenticated liveness view of Master Blaster, shaped for Uptime Kuma.

    Returns 200 when the node is usable OR deliberately away for gaming, and 503
    only when it is genuinely unreachable with no explanation.

    Kuma's monitor 24 used to probe MB's Ollama port directly, which would have
    gone red for the entire length of every gaming session once the GPU gate
    landed - trading one kind of alert noise for another. Point that monitor
    here instead.
    """
    payload = reaper.status_payload()
    status = payload.get("status")
    body = {
        "node": "master-blaster",
        "status": status,
        "gate": reaper.get_gate_report(),
    }
    if status in ("up", "away"):
        return jsonify(body), 200
    body["detail"] = payload.get("detail") or payload.get("error")
    return jsonify(body), 503


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


def _parse_generation_native(data: bytes, duration_ms: int) -> dict | None:
    """Parse token metrics from Ollama native /api/generate or /api/chat response."""
    try:
        parsed = json.loads(data)
        eval_count = parsed.get("eval_count", 0)
        prompt_eval_count = parsed.get("prompt_eval_count", 0)
        if not eval_count:
            return None
        seconds = duration_ms / 1000
        eval_dur_ns = parsed.get("eval_duration", 0)
        gen_seconds = eval_dur_ns / 1e9 if eval_dur_ns else seconds
        gen_tps = round(eval_count / gen_seconds, 2) if gen_seconds > 0 else 0
        prompt_dur_ns = parsed.get("prompt_eval_duration", 0)
        if prompt_dur_ns and prompt_eval_count:
            prompt_tps = round(prompt_eval_count / (prompt_dur_ns / 1e9), 2)
        else:
            prompt_tps = 0
        return {
            "generated_tokens": eval_count,
            "seconds": round(seconds, 2),
            "generate_tps": gen_tps,
            "prompt_tps": prompt_tps,
            "context": prompt_eval_count + eval_count,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("_parse_generation_native failed: %s", exc)
        return None


def _parse_embed_stats(data: bytes, duration_ms: int) -> dict | None:
    """Extract prompt token count from Ollama embed response for traffic display."""
    try:
        parsed = json.loads(data)
        prompt_tokens = parsed.get("prompt_eval_count", 0)
        if not prompt_tokens:
            return None
        seconds = duration_ms / 1000
        tps = round(prompt_tokens / seconds, 2) if seconds > 0 else 0
        return {
            "generated_tokens": 0,
            "seconds": round(seconds, 2),
            "generate_tps": 0,
            "prompt_tps": tps,
            "context": prompt_tokens,
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("_parse_embed_stats failed: %s", exc)
        return None


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
    port = int(os.environ.get("PORT", "8793"))
    app.run(host="0.0.0.0", port=port, debug=False)
