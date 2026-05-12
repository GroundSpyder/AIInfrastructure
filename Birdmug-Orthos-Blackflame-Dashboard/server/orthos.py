"""Orthos API client — proxies requests to Chris's Orthos upstream."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

ORTHOS_BASE_URL = os.environ.get(
    "ORTHOS_BASE_URL", "https://chris13600k.tail406192.ts.net/v1"
).rstrip("/")
ORTHOS_API_TOKEN = os.environ.get("ORTHOS_API_TOKEN", "")
TEST_MODEL = os.environ.get(
    "ORTHOS_TEST_MODEL", "Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6"
)


def request_json(
    path: str, method: str = "GET", payload: dict | None = None, timeout: int = 45
) -> tuple[int, dict, dict[str, str]]:
    if not ORTHOS_API_TOKEN:
        raise RuntimeError("ORTHOS_API_TOKEN is not set")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{ORTHOS_BASE_URL}{path}", data=body, method=method)
    req.add_header("Authorization", f"Bearer {ORTHOS_API_TOKEN}")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return response.status, data, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except Exception:  # parse failure — fall back to raw string, not a silent drop
            data = {"error": raw or str(exc)}
        return exc.code, data, dict(exc.headers.items())


def status_payload() -> dict:
    code, data, _ = request_json("/orthos/status", timeout=20)
    if code != 200:
        return {"status": "down", "error": data, "ts": time.time()}
    models_code, models_data, _ = request_json("/models", timeout=20)
    found = (
        [
            m.get("id", "")
            for m in (models_data.get("data", []) if isinstance(models_data, dict) else [])
            if isinstance(m, dict) and m.get("id")
        ]
        if models_code == 200
        else []
    )
    data["model"] = {
        "available": TEST_MODEL in found,
        "id": TEST_MODEL,
        "models": found,
    }
    return data


def health_test() -> dict:
    started = time.time()
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        status_code, models, _ = request_json("/models", timeout=20)
        found = [
            m.get("id", "")
            for m in models.get("data", [])
            if isinstance(m, dict) and m.get("id")
        ]
        add(
            "Models endpoint",
            status_code == 200 and TEST_MODEL in found,
            ", ".join(found) if found else str(models),
        )
    except Exception as exc:
        add("Models endpoint", False, str(exc))

    try:
        status_code, data, headers = request_json(
            "/chat/completions",
            method="POST",
            payload={
                "model": TEST_MODEL,
                "messages": [{"role": "user", "content": "Reply exactly: dashboard ok"}],
                "max_tokens": 8,
                "temperature": 0,
            },
            timeout=120,
        )
        if status_code == 429:
            add(
                "Chat completion",
                False,
                f"Queued too long; retry after {headers.get('Retry-After', '30')}s",
            )
        else:
            content = (
                str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
                .strip()
                .lower()
            )
            add(
                "Chat completion",
                status_code == 200 and "dashboard ok" in content,
                content or str(data),
            )
    except Exception as exc:
        add("Chat completion", False, str(exc))

    failed = sum(1 for check in checks if not check["ok"])
    return {
        "ok": failed == 0,
        "failed": failed,
        "checks": checks,
        "duration_ms": int((time.time() - started) * 1000),
        "ts": time.time(),
    }
