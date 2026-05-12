"""LilBlue (Kaydanski Ollama) API client."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from server.tracker import tracker

log = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://kaydanskipc:11434").rstrip("/")
TEST_MODEL = os.environ.get("LILBLUE_TEST_MODEL", "qwen2.5:7b")


def request_json(
    path: str, method: str = "GET", payload: dict | None = None, timeout: int = 30
) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:  # parse failure — fall back to raw string, not a silent drop
            data = {"error": raw or str(exc)}
        return exc.code, data


def status_payload() -> dict:
    try:
        code, version_data = request_json("/api/version", timeout=10)
        if code != 200:
            return {"status": "down", "error": version_data, "ts": time.time()}
        version = version_data.get("version", "unknown") if isinstance(version_data, dict) else "unknown"
    except Exception as exc:
        return {"status": "down", "error": str(exc), "ts": time.time()}

    try:
        _, ps_data = request_json("/api/ps", timeout=10)
        loaded = ps_data.get("models", []) if isinstance(ps_data, dict) else []
    except Exception as exc:
        log.warning("LilBlue /api/ps failed: %s", exc)
        loaded = []

    try:
        _, tags_data = request_json("/api/tags", timeout=10)
        available = tags_data.get("models", []) if isinstance(tags_data, dict) else []
    except Exception as exc:
        log.warning("LilBlue /api/tags failed: %s", exc)
        available = []

    available_names = {m.get("name") or m.get("model", "") for m in available if m.get("name") or m.get("model")}
    model_available = TEST_MODEL in available_names

    t = tracker.status()
    return {
        "status": "up",
        "version": version,
        "model": {"id": TEST_MODEL, "available": model_available},
        "loaded": loaded,
        "available": available,
        "current": t["current"],
        "traffic": t["traffic"],
        "performance": t["performance"],
        "ts": time.time(),
    }


def health_test() -> dict:
    started = time.time()
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        code, data = request_json("/api/version", timeout=10)
        add("Ollama reachable", code == 200,
            data.get("version", str(data)) if isinstance(data, dict) else str(data))
    except Exception as exc:
        add("Ollama reachable", False, str(exc))

    try:
        code, data = request_json("/api/tags", timeout=10)
        models = data.get("models", []) if isinstance(data, dict) else []
        add("Model list", code == 200, f"{len(models)} model(s) installed")
    except Exception as exc:
        add("Model list", False, str(exc))

    try:
        code, data = request_json(
            "/api/generate",
            method="POST",
            payload={
                "model": TEST_MODEL,
                "prompt": "Reply with only the word: ok",
                "stream": False,
                "options": {"num_predict": 5},
            },
            timeout=90,
        )
        response_text = (
            data.get("response", "").strip().lower() if isinstance(data, dict) else ""
        )
        add("Generate", code == 200, response_text or str(data))
    except Exception as exc:
        add("Generate", False, str(exc))

    failed = sum(1 for c in checks if not c["ok"])
    return {
        "ok": failed == 0,
        "failed": failed,
        "checks": checks,
        "duration_ms": int((time.time() - started) * 1000),
        "ts": time.time(),
    }
