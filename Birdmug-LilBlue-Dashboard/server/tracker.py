"""In-memory request metrics tracker — mirrors Orthos's counter/perf structure."""

from __future__ import annotations

import threading
import time
from collections import deque


def _fmt_generation(gen: dict | None) -> str:
    if not gen:
        return ""
    t = gen.get("generated_tokens", 0)
    s = gen.get("seconds", 0)
    tps = gen.get("generate_tps", 0)
    ctx = gen.get("context", 0)
    return f"{t} tokens in {s:.2f}s, {tps:.1f} T/s, context {ctx}"


def _count_window(metrics: list[dict], since: float) -> dict:
    r = {"requests": 0, "success": 0, "unauthorized": 0, "blocked": 0, "upstream_errors": 0, "rate_limited": 0}
    for m in metrics:
        if m["ts"] < since:
            break
        r["requests"] += 1
        s = m.get("status", 0)
        if 200 <= s < 300:
            r["success"] += 1
        elif s == 401:
            r["unauthorized"] += 1
        elif s == 503:
            r["blocked"] += 1
        elif s == 429:
            r["rate_limited"] += 1
        elif s >= 500:
            r["upstream_errors"] += 1
    return r


def _perf_window(metrics: list[dict], since: float) -> dict:
    tokens = 0
    reqs = 0
    tps_sum = 0.0
    tps_count = 0
    max_ctx = 0
    for m in metrics:
        if m["ts"] < since:
            break
        reqs += 1
        gen = m.get("generation")
        if gen:
            tokens += gen.get("generated_tokens", 0)
            tps = gen.get("generate_tps", 0)
            if tps:
                tps_sum += tps
                tps_count += 1
            ctx = gen.get("context", 0)
            if ctx > max_ctx:
                max_ctx = ctx
    return {
        "tokens": tokens,
        "requests": reqs,
        "avg_generate_tps": round(tps_sum / tps_count, 1) if tps_count else 0,
        "max_context": max_ctx,
    }


class MetricsTracker:
    def __init__(self, maxlen: int = 200):
        self._lock = threading.Lock()
        self._metrics: deque[dict] = deque(maxlen=maxlen)
        self._current: dict = {}
        self._latest_perf: dict = {}

    def start(self, method: str, path: str, model: str = "") -> None:
        with self._lock:
            self._current = {"method": method, "path": path, "model": model, "started": time.time()}

    def finish(self, status: int, duration_ms: int, queue_ms: int = 0, model: str = "", generation: dict | None = None) -> None:
        with self._lock:
            entry = {
                "ts": time.time(),
                "method": self._current.get("method", ""),
                "path": self._current.get("path", ""),
                "status": status,
                "duration_ms": duration_ms,
                "queue_ms": queue_ms,
                "model": model or self._current.get("model", ""),
                "generation": generation,
                "category": _fmt_generation(generation),
            }
            self._metrics.appendleft(entry)
            self._current = {}
            if generation:
                self._latest_perf = {
                    "generate_tps": generation.get("generate_tps", 0),
                    "prompt_tps": generation.get("prompt_tps", 0),
                    "generated_tokens": generation.get("generated_tokens", 0),
                }

    def current(self) -> dict:
        with self._lock:
            return dict(self._current)

    def status(self) -> dict:
        with self._lock:
            now = time.time()
            metrics = list(self._metrics)
            latest = dict(self._latest_perf)
            current = dict(self._current)
        return {
            "current": current,
            "traffic": {
                "counters": {
                    "last_5_minutes": _count_window(metrics, now - 300),
                    "last_hour": _count_window(metrics, now - 3600),
                },
                "metrics": metrics[:40],
            },
            "performance": {
                "latest": latest,
                "windows": {
                    "1h": _perf_window(metrics, now - 3600),
                    "12h": _perf_window(metrics, now - 43200),
                    "24h": _perf_window(metrics, now - 86400),
                },
            },
        }


tracker = MetricsTracker()
