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
    ctx = gen.get("context", 0)
    if t == 0 and ctx > 0:
        # Embedding: no generated tokens, report prompt throughput against context
        ptps = gen.get("prompt_tps", 0)
        return f"{ctx} tokens embedded in {s:.2f}s, {ptps:.1f} T/s"
    tps = gen.get("generate_tps", 0)
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
        # _inflight: id() -> {method, path, model, started} for every concurrent
        # request currently being proxied. gthread can run many at once, so a
        # single shared "current" slot would race and clobber metadata.
        self._inflight: dict[int, dict] = {}
        self._latest_perf: dict = {}

    def start(self, method: str, path: str, model: str = "") -> int:
        """Begin tracking a request. Returns a token to pass back to finish()."""
        entry = {"method": method, "path": path, "model": model, "started": time.time()}
        token = id(entry)
        with self._lock:
            self._inflight[token] = entry
        return token

    def finish(self, token: int, status: int, duration_ms: int, queue_ms: int = 0, model: str = "", generation: dict | None = None) -> None:
        with self._lock:
            started = self._inflight.pop(token, {})
            entry = {
                "ts": time.time(),
                "method": started.get("method", ""),
                "path": started.get("path", ""),
                "status": status,
                "duration_ms": duration_ms,
                "queue_ms": queue_ms,
                "model": model or started.get("model", ""),
                "generation": generation,
                "category": _fmt_generation(generation),
            }
            self._metrics.appendleft(entry)
            if generation and generation.get("generated_tokens", 0) > 0:
                self._latest_perf = {
                    "generate_tps": generation.get("generate_tps", 0),
                    "prompt_tps": generation.get("prompt_tps", 0),
                    "generated_tokens": generation.get("generated_tokens", 0),
                }

    def current(self) -> dict:
        """Return the oldest in-flight request, or {} if idle. Dashboard shows one."""
        with self._lock:
            if not self._inflight:
                return {}
            return dict(min(self._inflight.values(), key=lambda e: e["started"]))

    def gc_stale(self, max_age_seconds: float = 600) -> int:
        """Drop _inflight entries older than max_age. Backstops leaked tokens
        from client-disconnect mid-stream or any other path where finish()
        never gets called. Returns count removed."""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            stale = [tok for tok, e in self._inflight.items() if e["started"] < cutoff]
            for tok in stale:
                self._inflight.pop(tok, None)
            return len(stale)

    def status(self) -> dict:
        self.gc_stale()
        with self._lock:
            now = time.time()
            metrics = list(self._metrics)
            latest = dict(self._latest_perf)
            current = dict(min(self._inflight.values(), key=lambda e: e["started"])) if self._inflight else {}
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
