"""Model-management API for the two Ollama hosts.

Routes (all gated by BirdMug-Auth via @require_auth on the blueprint):

  GET    /api/models/hosts                 -> host registry (label, gpu, backend)
  GET    /api/models/<host>/ps             -> currently loaded models (Ollama /api/ps)
  GET    /api/models/<host>/tags           -> installed models (Ollama /api/tags)
  POST   /api/models/<host>/show           -> model details (body: {model})
  POST   /api/models/<host>/load           -> warm into VRAM (body: {model, strict_gpu, keep_alive})
  POST   /api/models/<host>/unload         -> evict (body: {model})
  POST   /api/models/<host>/pull           -> pull new model — streams SSE
  DELETE /api/models/<host>/delete         -> delete (body: {model, confirm_name})
  GET    /api/models/<host>/env            -> NSSM AppEnvironmentExtra dict
  PUT    /api/models/<host>/env            -> replace NSSM env (body: {env: {...}})
  POST   /api/models/<host>/restart-ollama -> restart OllamaService via NSSM
  GET    /api/models/<host>/warm-set       -> read warm-set.json on host (via SSH)
  PUT    /api/models/<host>/warm-set       -> write warm-set.json + nothing else
  GET    /api/audit                        -> last 200 audit entries

No silent failures: every route surfaces real errors with status code
and message. SSHError, requests.RequestException, JSON parse errors
all turn into 502 / 504 responses with the actual upstream error in
the body so the dashboard can show it in a toast.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

# POSIX env-var name convention: ASCII letters/digits/underscore, no
# leading digit. NSSM is happy with anything the OS env block accepts,
# but tighter is better — rules out unicode lookalikes that could
# confuse later inspection.
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

from server.audit import record as audit_record
from server.audit import tail as audit_tail
from server.auth import require_auth
from server.fleet_ssh import HOSTS, SSHError, get_nssm_env, read_remote_file
from server.fleet_ssh import restart_service as ssh_restart_service
from server.fleet_ssh import run_remote, set_nssm_env, write_remote_file

log = logging.getLogger(__name__)

bp = Blueprint("models_api", __name__, url_prefix="/api")


def _user_for_audit() -> str:
    """Best-effort user identifier for the audit log.

    Extracts the JWT `sub` if present; otherwise falls back to remote IP.
    Auth decoding has already happened in require_auth, but we re-parse
    here without raising because the audit log shouldn't fail the call.
    """
    import os

    import jwt as _jwt

    token = None
    for name in ("birdmug_token", "bm_token"):
        v = request.cookies.get(name)
        if v:
            token = v
            break
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        try:
            secret = os.environ.get("BIRDMUG_JWT_SECRET", "")
            if secret:
                payload = _jwt.decode(
                    token, secret, algorithms=["HS256"], options={"verify_aud": False, "verify_iss": False}
                )
                return payload.get("sub") or payload.get("email") or "auth"
        except _jwt.InvalidTokenError as e:
            # require_auth already passed by the time we get here, so an
            # invalid token at this stage means JWT shape changed mid-
            # request or the audit decode is misaligned with auth.py.
            # Worth surfacing rather than silently downgrading to IP.
            log.warning("audit jwt decode failed (req passed auth gate): %s", e)
    return request.remote_addr or "?"


def _require_host(alias: str):
    if alias not in HOSTS:
        return None, (jsonify({"error": "unknown host", "host": alias}), 404)
    return HOSTS[alias], None


# ---------------------------------------------------------------------------
# Read-only inspection (Phase 1)
# ---------------------------------------------------------------------------


@bp.get("/models/hosts")
@require_auth
def list_hosts():
    return jsonify(
        {
            "hosts": [
                {
                    "alias": h.alias,
                    "label": h.label,
                    "gpu": h.gpu_name,
                    "backend": h.backend,
                }
                for h in HOSTS.values()
            ]
        }
    )


@bp.get("/models/<alias>/ps")
@require_auth
def ps(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    try:
        r = requests.get(f"{spec.ollama_url}/api/ps", timeout=10)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        return jsonify({"error": "upstream_unreachable", "host": alias, "detail": str(e)}), 502


@bp.get("/models/<alias>/tags")
@require_auth
def tags(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    try:
        r = requests.get(f"{spec.ollama_url}/api/tags", timeout=15)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        return jsonify({"error": "upstream_unreachable", "host": alias, "detail": str(e)}), 502


@bp.post("/models/<alias>/show")
@require_auth
def show(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    model = body.get("model")
    if not model:
        return jsonify({"error": "missing 'model'"}), 400
    try:
        r = requests.post(f"{spec.ollama_url}/api/show", json={"model": model}, timeout=10)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        return jsonify({"error": "upstream_unreachable", "host": alias, "detail": str(e)}), 502


# ---------------------------------------------------------------------------
# Load / Unload (Phase 2)
# ---------------------------------------------------------------------------


def _ollama_warm(spec, model: str, *, strict_gpu: bool, keep_alive: str) -> dict[str, Any]:
    """Warm a model into VRAM via /api/generate with empty prompt.

    `strict_gpu=True` sets num_gpu=999 so Ollama tries to put all layers
    on the GPU; if the model doesn't fit, the call surfaces an error
    (instead of silently spilling to CPU). `strict_gpu=False` omits
    num_gpu so Ollama's auto-detect splits layers between GPU and CPU.
    """
    options: dict[str, Any] = {}
    if strict_gpu:
        options["num_gpu"] = 999
    body = {"model": model, "prompt": "", "keep_alive": keep_alive, "options": options}
    r = requests.post(f"{spec.ollama_url}/api/generate", json=body, timeout=120)
    r.raise_for_status()
    return r.json()


@bp.post("/models/<alias>/load")
@require_auth
def load_model(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    model = body.get("model")
    if not model:
        return jsonify({"error": "missing 'model'"}), 400
    strict_gpu = bool(body.get("strict_gpu", False))
    keep_alive = body.get("keep_alive", "24h")
    user = _user_for_audit()
    try:
        result = _ollama_warm(spec, model, strict_gpu=strict_gpu, keep_alive=keep_alive)
        audit_record(
            "load", host=alias, model=model, user=user, status="ok",
            strict_gpu=strict_gpu, keep_alive=keep_alive,
        )
        return jsonify({"status": "loaded", "model": model, "ollama": result})
    except requests.RequestException as e:
        msg = _ollama_error_message(e)
        audit_record("load", host=alias, model=model, user=user, status="fail", error=msg)
        return jsonify({"error": "ollama_error", "host": alias, "detail": msg}), 502


@bp.post("/models/<alias>/unload")
@require_auth
def unload_model(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    model = body.get("model")
    if not model:
        return jsonify({"error": "missing 'model'"}), 400
    user = _user_for_audit()
    try:
        r = requests.post(
            f"{spec.ollama_url}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": "0s"},
            timeout=30,
        )
        r.raise_for_status()
        audit_record("unload", host=alias, model=model, user=user, status="ok")
        return jsonify({"status": "unloaded", "model": model})
    except requests.RequestException as e:
        msg = _ollama_error_message(e)
        audit_record("unload", host=alias, model=model, user=user, status="fail", error=msg)
        return jsonify({"error": "ollama_error", "host": alias, "detail": msg}), 502


# ---------------------------------------------------------------------------
# Pull / Delete (Phase 3)
# ---------------------------------------------------------------------------


@bp.post("/models/<alias>/pull")
@require_auth
def pull_model(alias: str):
    """Stream pull progress as Server-Sent Events.

    Ollama's /api/pull emits NDJSON — one JSON object per line — with
    `{status, digest?, total?, completed?}`. We re-emit each line as
    an SSE `data:` frame so the dashboard can show a progress bar
    and the final outcome. On terminal status we audit-log.
    """
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    model = body.get("model")
    if not model:
        return jsonify({"error": "missing 'model'"}), 400
    user = _user_for_audit()

    def gen():
        last_status = None
        try:
            with requests.post(
                f"{spec.ollama_url}/api/pull",
                json={"model": model, "stream": True},
                stream=True,
                timeout=(10, None),  # 10s connect, no read timeout — pulls can take hours
            ) as r:
                r.raise_for_status()
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        # Surface upstream garble rather than swallow
                        yield f"event: error\ndata: {json.dumps({'raw': raw[:500]})}\n\n"
                        continue
                    last_status = evt.get("status", last_status)
                    yield f"data: {json.dumps(evt)}\n\n"
                    if evt.get("error"):
                        audit_record(
                            "pull", host=alias, model=model, user=user, status="fail",
                            error=str(evt.get("error")),
                        )
                        return
            # Successful end-of-stream
            audit_record("pull", host=alias, model=model, user=user, status="ok", last_status=last_status)
            yield f"event: done\ndata: {json.dumps({'status': last_status or 'success'})}\n\n"
        except requests.RequestException as e:
            msg = _ollama_error_message(e)
            audit_record("pull", host=alias, model=model, user=user, status="fail", error=msg)
            yield f"event: error\ndata: {json.dumps({'detail': msg})}\n\n"

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@bp.delete("/models/<alias>/delete")
@require_auth
def delete_model(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    model = body.get("model")
    confirm = body.get("confirm_name")
    if not model:
        return jsonify({"error": "missing 'model'"}), 400
    if confirm != model:
        return jsonify(
            {"error": "confirmation_required", "detail": "confirm_name must exactly match model"}
        ), 400
    user = _user_for_audit()
    try:
        r = requests.delete(f"{spec.ollama_url}/api/delete", json={"model": model}, timeout=30)
        r.raise_for_status()
        audit_record("delete", host=alias, model=model, user=user, status="ok")
        return jsonify({"status": "deleted", "model": model})
    except requests.RequestException as e:
        msg = _ollama_error_message(e)
        audit_record("delete", host=alias, model=model, user=user, status="fail", error=msg)
        return jsonify({"error": "ollama_error", "host": alias, "detail": msg}), 502


# ---------------------------------------------------------------------------
# NSSM env + service restart (Phase 4) — SSH control plane
# ---------------------------------------------------------------------------


@bp.get("/models/<alias>/env")
@require_auth
def get_env(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    try:
        env = get_nssm_env(alias)
        return jsonify({"host": alias, "env": env})
    except SSHError as e:
        return jsonify({"error": "ssh_failed", "host": alias, "detail": str(e)}), 502


@bp.put("/models/<alias>/env")
@require_auth
def put_env(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    env = body.get("env")
    if not isinstance(env, dict):
        return jsonify({"error": "missing or invalid 'env' object"}), 400
    # Validate: keys must look like env vars (alphanumeric + underscore).
    # Values must be strings without control characters — both because
    # control chars aren't valid env-var content, and because they'd
    # break the PowerShell single-quoted literal that wraps them in
    # fleet_ssh.set_nssm_env. Length-cap to avoid pathological inputs.
    for k, v in env.items():
        if not isinstance(k, str) or not _ENV_KEY_RE.match(k):
            return jsonify({"error": f"invalid env key: {k!r}"}), 400
        if not isinstance(v, str):
            return jsonify({"error": f"env value for {k!r} must be a string"}), 400
        if len(v) > 2048:
            return jsonify({"error": f"env value for {k!r} too long (max 2048)"}), 400
        if any(ord(c) < 0x20 for c in v):
            return jsonify({"error": f"env value for {k!r} contains control characters"}), 400
    user = _user_for_audit()
    try:
        set_nssm_env(alias, env)
        audit_record("env_set", host=alias, user=user, status="ok", env_keys=sorted(env.keys()))
        return jsonify({"status": "ok", "host": alias, "env": env, "restart_required": True})
    except SSHError as e:
        audit_record("env_set", host=alias, user=user, status="fail", error=str(e))
        return jsonify({"error": "ssh_failed", "host": alias, "detail": str(e)}), 502


@bp.post("/models/<alias>/restart-ollama")
@require_auth
def restart_ollama(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    user = _user_for_audit()
    try:
        out = ssh_restart_service(alias)
        audit_record("restart_ollama", host=alias, user=user, status="ok", nssm_output=out[:500])
        return jsonify({"status": "restarted", "host": alias, "nssm_output": out})
    except SSHError as e:
        audit_record("restart_ollama", host=alias, user=user, status="fail", error=str(e))
        return jsonify({"error": "ssh_failed", "host": alias, "detail": str(e)}), 502


# ---------------------------------------------------------------------------
# Warm-set editor (Phase 5) — read/write warm-set.json on each host
# ---------------------------------------------------------------------------

WARM_SET_PATH = {
    "mb":        r"C:\falkensteink\AIInfrastructure\master-blaster-ai-control\warm-set.json",
    "kaydanski": r"C:\Users\Kaiden\ollama-warm-set.json",
}


@bp.get("/models/<alias>/warm-set")
@require_auth
def get_warm_set(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    path = WARM_SET_PATH.get(alias)
    if not path:
        return jsonify({"error": "no warm-set path configured for host"}), 404
    try:
        content = read_remote_file(alias, path)
    except SSHError as e:
        return jsonify({"error": "ssh_failed", "host": alias, "detail": str(e)}), 502
    if content is None:
        # File-missing is the common case before the first ever write.
        # read_remote_file uses a Test-Path probe + sentinel so we don't
        # have to substring-match SSH stderr to detect this.
        return jsonify(
            {"host": alias, "warm_set": _default_warm_set(), "path": path, "exists": False}
        )
    if not content.strip():
        # Empty or whitespace-only file is corruption — distinct from
        # missing. Refusing to substitute {} prevents the dashboard
        # from silently overwriting real data with an empty default.
        return jsonify(
            {"error": "corrupt_warm_set", "host": alias, "detail": "remote file is empty"}
        ), 500
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return jsonify({"error": "corrupt_warm_set", "host": alias, "detail": str(e)}), 500
    return jsonify({"host": alias, "warm_set": data, "path": path})


@bp.put("/models/<alias>/warm-set")
@require_auth
def put_warm_set(alias: str):
    spec, err = _require_host(alias)
    if err:
        return err
    path = WARM_SET_PATH.get(alias)
    if not path:
        return jsonify({"error": "no warm-set path configured for host"}), 404
    body = request.get_json(silent=True) or {}
    warm_set = body.get("warm_set")
    if not isinstance(warm_set, dict):
        return jsonify({"error": "missing or invalid 'warm_set' object"}), 400
    chat = warm_set.get("chat", [])
    embed = warm_set.get("embed", [])
    if not (isinstance(chat, list) and isinstance(embed, list)):
        return jsonify({"error": "'chat' and 'embed' must be arrays of model names"}), 400
    for m in chat + embed:
        if not isinstance(m, str) or not m:
            return jsonify({"error": "model names must be non-empty strings"}), 400
    user = _user_for_audit()
    payload = json.dumps({"chat": chat, "embed": embed}, indent=2)
    try:
        write_remote_file(alias, path, payload)
        audit_record(
            "warm_set_write", host=alias, user=user, status="ok",
            chat_count=len(chat), embed_count=len(embed),
        )
        return jsonify({"status": "ok", "host": alias, "warm_set": {"chat": chat, "embed": embed}})
    except SSHError as e:
        audit_record("warm_set_write", host=alias, user=user, status="fail", error=str(e))
        return jsonify({"error": "ssh_failed", "host": alias, "detail": str(e)}), 502


def _default_warm_set() -> dict[str, list[str]]:
    return {"chat": [], "embed": []}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@bp.get("/audit")
@require_auth
def audit():
    return jsonify({"entries": audit_tail(limit=200)})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ollama_error_message(e: requests.RequestException) -> str:
    """Pull the actual upstream error message out of a RequestException.

    Ollama usually returns JSON {"error":"model not found"} on 4xx. We
    prefer that string. If the body isn't that shape — different key,
    a list wrapper, null in `error` but a message elsewhere — we
    surface the raw body (truncated) rather than masking it with a
    generic str(e). Hides nothing.
    """
    resp = getattr(e, "response", None)
    if resp is None:
        return str(e) or e.__class__.__name__
    try:
        data = resp.json()
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, str) and err:
            return f"{resp.status_code}: {err}"
        # Unknown JSON shape — pass it through verbatim
        return f"{resp.status_code}: {json.dumps(data)[:500]}"
    if data is not None:
        # Non-dict JSON (list, scalar) — surface verbatim
        return f"{resp.status_code}: {json.dumps(data)[:500]}"
    text = (resp.text or "").strip()
    if text:
        return f"{resp.status_code}: {text[:500]}"
    return f"{resp.status_code}: <empty body>"
