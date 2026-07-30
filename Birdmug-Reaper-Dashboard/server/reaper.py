"""Reaper (Master Blaster Ollama) API client."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

from server.tracker import tracker

log = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://192.168.4.33:11434").rstrip("/")
TEST_MODEL = os.environ.get("REAPER_TEST_MODEL", "qwen3:14b")


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


def is_node_away(exc: BaseException) -> bool:
    """True when the failure means "Master Blaster is not accepting connections".

    Master Blaster is Kyle's gaming PC. Game-Watch.ps1 there STOPS OllamaService
    for the duration of a gaming session, so this node vanishing for hours is a
    designed operating state, not an incident. It is also simply off sometimes.

    Distinguishing this from a genuine fault matters because reaper-dashboard
    filed 7,946 Bug Fairy reports between 2026-07-09 and 2026-07-30 - 745 of them
    literally "URLError: <urlopen error [Errno 113] No route to host>" - for a
    machine that was intentionally unavailable. Reporting an expected absence as
    an error trains everyone to ignore the error channel, which is the real cost.

    A genuine upstream fault (bad gateway, TLS failure, DNS misconfiguration)
    still returns False here and is still captured.
    """
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, (ConnectionRefusedError, ConnectionResetError)):
        return True
    if isinstance(reason, OSError) and reason.errno in (111, 113):
        # 111 ECONNREFUSED - Master Blaster is up but nothing is listening
        #                    (exactly what the gaming gate produces)
        # 113 EHOSTUNREACH  - the host itself is not answering
        #
        # Deliberately NOT 101 ENETUNREACH: that means THIS container has no
        # route out at all, which is a Toshi networking fault, not Master
        # Blaster being away. Classifying it as "expected" would silence a real
        # local outage.
        return True
    text = str(reason).lower()
    return any(
        marker in text
        for marker in (
            "connection refused",
            "no route to host",
            "host is unreachable",
        )
    )


AWAY_HINT = (
    "Master Blaster stops Ollama while a game is running. It rejoins the fleet "
    "automatically when the game exits."
)

# How long a gate heartbeat from Master Blaster stays trustworthy. The watcher
# pushes one every poll (~10s), so a minute of silence means the watcher, the
# network, or the whole machine is gone - none of which are "away by design".
GATE_HEARTBEAT_TTL_SECONDS = int(os.environ.get("GATE_HEARTBEAT_TTL_SECONDS", "90"))

# How long an absence stays "expected". Beyond this we call it a fault even if
# the gate is still dutifully reporting a pause - a gaming session does not last
# a day, and Game-Watch deliberately leaves the gate PAUSED when OllamaService
# fails to restart, which would otherwise look identical to gaming forever.
AWAY_BUDGET_HOURS = float(os.environ.get("AWAY_BUDGET_HOURS", "12"))

_gate_lock = threading.Lock()
_gate_report: dict | None = None
_away_since: float | None = None


def note_node_reachable() -> None:
    """Clear the away timer. Called whenever the upstream answers normally."""
    global _away_since
    with _gate_lock:
        _away_since = None


def _away_duration_hours() -> float | None:
    """Hours since the node first became unreachable, starting the clock now if
    this is the first observation."""
    global _away_since
    now = time.time()
    with _gate_lock:
        if _away_since is None:
            _away_since = now
            return 0.0
        return (now - _away_since) / 3600.0


def record_gate_state(payload: dict) -> dict:
    """Store the latest gate heartbeat pushed by Master Blaster's watcher."""
    entry = {
        "state": str(payload.get("state", ""))[:32],
        "owner": str(payload.get("owner", ""))[:32],
        "reason": str(payload.get("reason", ""))[:200],
        "game": str(payload.get("game", ""))[:100],
        "received_at": time.time(),
    }
    global _gate_report
    with _gate_lock:
        _gate_report = entry
    return entry


def get_gate_report() -> dict | None:
    """Latest heartbeat if it is still fresh, else None.

    Returning None for a stale heartbeat is the whole point: it is what lets
    an unreachable Ollama be classified as a genuine outage rather than as an
    expected gaming pause.
    """
    with _gate_lock:
        entry = _gate_report
    if not entry:
        return None
    age = time.time() - entry["received_at"]
    if age > GATE_HEARTBEAT_TTL_SECONDS:
        return None
    return dict(entry, age_seconds=round(age, 1))


def status_payload() -> dict:
    try:
        code, version_data = request_json("/api/version", timeout=10)
        if code != 200:
            return {"status": "down", "error": version_data, "ts": time.time()}
        version = version_data.get("version", "unknown") if isinstance(version_data, dict) else "unknown"
        note_node_reachable()
    except Exception as exc:
        # "away" and "down" are different facts and the dashboard renders them
        # differently: away is a calm expected state, down is a fault worth
        # chasing. Collapsing them into one was what made three weeks of
        # deliberate absence look like an outage.
        #
        # A refused connection alone is NOT enough to claim "away" - a dead PSU
        # looks exactly the same from here. We only downgrade to "away" when
        # Master Blaster's watcher has recently told us it paused on purpose.
        # No fresh heartbeat means we do not know, and not-knowing is reported
        # as "down" so it still gets attention.
        if is_node_away(exc):
            gate = get_gate_report()
            if gate and gate.get("state") == "paused":
                # Time-box it. "Away" is expected for the length of a gaming
                # session, not for days. Past the budget we stop calling this
                # normal, so a machine that is wedged-but-heartbeating (or a
                # gate stuck paused because OllamaService will not start) still
                # gets attention instead of hiding behind a calm amber card.
                away_hours = _away_duration_hours()
                if away_hours is not None and away_hours > AWAY_BUDGET_HOURS:
                    return {
                        "status": "down",
                        "error": str(exc),
                        "detail": (
                            f"Master Blaster has been gated for {away_hours:.1f}h, "
                            f"beyond the {AWAY_BUDGET_HOURS}h expected-gaming budget. "
                            "Treating this as a fault rather than a normal pause."
                        ),
                        "gate": gate,
                        "ts": time.time(),
                    }
                return {
                    "status": "away",
                    "error": str(exc),
                    "hint": AWAY_HINT,
                    "gate": gate,
                    "away_hours": away_hours,
                    "ts": time.time(),
                }
            return {
                "status": "down",
                "error": str(exc),
                "detail": (
                    "Ollama is unreachable and Master Blaster has not reported a "
                    "gaming pause recently, so this is not an expected absence."
                ),
                "ts": time.time(),
            }
        return {"status": "down", "error": str(exc), "ts": time.time()}

    try:
        _, ps_data = request_json("/api/ps", timeout=10)
        loaded = ps_data.get("models", []) if isinstance(ps_data, dict) else []
    except Exception as exc:
        log.warning("Reaper /api/ps failed: %s", exc)
        loaded = []

    try:
        _, tags_data = request_json("/api/tags", timeout=10)
        available = tags_data.get("models", []) if isinstance(tags_data, dict) else []
    except Exception as exc:
        log.warning("Reaper /api/tags failed: %s", exc)
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
