#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ORTHOS_BASE_URL = os.environ.get(
    "ORTHOS_BASE_URL", "https://chris13600k.tail406192.ts.net/v1"
).rstrip("/")
ORTHOS_API_TOKEN = os.environ.get("ORTHOS_API_TOKEN", "")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8791"))
TEST_MODEL = os.environ.get(
    "ORTHOS_TEST_MODEL", "Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6"
)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Orthos API Dashboard</title>
  <link rel="icon" href="/favicon.ico?v=orthos-20260511" sizes="any">
  <link rel="shortcut icon" href="/favicon.ico?v=orthos-20260511">
  <style>
    :root { color-scheme: dark; --bg:#030303; --panel:#0b0b0c; --panel2:#141416; --line:#3a3a3d; --text:#f7f0e8; --muted:#9d9a96; --good:#25d58f; --bad:#ff2d16; --warn:#ff6a00; --blue:#f7f0e8; --ember:#ff3b14; --ash:#1d1f22; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 18% -10%, rgba(255, 45, 18, .30), transparent 31%), radial-gradient(circle at 82% -4%, rgba(255, 190, 24, .18), transparent 26%), linear-gradient(180deg, #070707, #020202 48%, #000); color:var(--text); }
    header { padding:18px 22px; border-bottom:1px solid #4e4e50; display:flex; align-items:center; justify-content:space-between; gap:16px; background:linear-gradient(90deg, rgba(2, 2, 2, .98), rgba(15, 15, 16, .94) 55%, rgba(60, 9, 2, .72)); box-shadow:0 10px 30px rgba(0,0,0,.50), inset 0 -1px 0 rgba(255, 82, 20, .25); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .brand-icon { width:32px; height:32px; flex:0 0 auto; }
    h1 { margin:0; font-size:22px; font-weight:700; color:#fff7dc; text-shadow:0 0 6px rgba(255, 240, 170, .55), 0 0 14px rgba(255, 96, 0, .95), 0 0 32px rgba(255, 32, 8, .72), 0 0 56px rgba(255, 150, 0, .36); }
    main { padding:20px; display:grid; gap:16px; max-width:1320px; margin:0 auto; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .grid3 { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; }
    .workgrid { display:grid; grid-template-columns: minmax(260px, .9fr) minmax(520px, 1.6fr); gap:16px; align-items:stretch; }
    .panel { background:linear-gradient(180deg, #161719, #080808); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.03); }
    .status-card { min-height:118px; overflow:hidden; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; margin-top:8px; line-height:1.22; overflow-wrap:anywhere; }
    .small { color:var(--muted); font-size:13px; line-height:1.45; }
    .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .blue { color:var(--blue); }
    button { border:1px solid #ff4a1a; background:linear-gradient(180deg, #25100b, #070707); color:#ffe7a0; border-radius:6px; padding:10px 13px; cursor:pointer; font-weight:650; box-shadow:inset 0 1px 0 rgba(255, 210, 74, .18); }
    button:hover { background:linear-gradient(180deg, #3c1208, #0b0b0b); border-color:#ff7a00; }
    .health-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; }
    .health-status { font-size:22px; font-weight:700; margin-top:6px; }
    .checks { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; margin-top:12px; }
    .check { border:1px solid var(--line); background:#0d0d0e; border-radius:6px; padding:9px 10px; min-height:64px; }
    .check.ok { border-color:#25d58f; background:#071812; }
    .check.fail { border-color:#ff2d16; background:#200b08; }
    .check .name { font-weight:700; }
    .check .detail { margin-top:4px; font-size:12px; color:var(--muted); overflow-wrap:anywhere; }
    .activebox { min-height:118px; max-height:178px; overflow:auto; margin:8px 0 0; white-space:pre-wrap; }
    .counter-grid { display:grid; grid-template-columns: repeat(5, minmax(82px, 1fr)); gap:8px; margin-top:10px; }
    .counter-card { border:1px solid var(--line); background:#0d0d0e; border-radius:6px; padding:9px; min-height:64px; }
    .counter-card .num { font-size:22px; font-weight:700; margin-top:4px; }
    .counter-card .name { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    .counter-tabs { display:flex; gap:8px; }
    .counter-tabs button { border-color:var(--line); background:#101112; padding:6px 9px; font-size:12px; }
    .counter-tabs button.active { border-color:#ff6a00; color:#fff1b8; background:#250b04; }
    .meter { height:8px; border-radius:999px; background:#020202; border:1px solid var(--line); overflow:hidden; margin-top:10px; }
    .meter > div { height:100%; background:linear-gradient(90deg, #ff1808, #ff6a00, #ffe95c); width:0%; box-shadow:0 0 14px rgba(255, 92, 0, .75); }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .table-scroll { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:6px; margin-top:10px; }
    .table-scroll table { min-width:760px; }
    .table-scroll thead th { position:sticky; top:0; background:var(--panel); z-index:1; }
    .status-pill { display:inline-block; min-width:42px; text-align:center; border-radius:999px; padding:2px 8px; font-weight:700; font-size:12px; border:1px solid var(--line); }
    .status-ok { background:#071812; color:#caffeb; border-color:#25d58f; }
    .status-503, .status-429 { background:#3a0b05; color:#ffd5c8; border-color:#ff2d16; }
    .status-error { background:#2b1705; color:#ffe2a8; border-color:#ff7a00; }
    tr.row-blocked td { background:rgba(255, 45, 22, .15); color:#ffd5c8; }
    tr.row-error td { background:rgba(255, 106, 0, .15); color:#ffe2a8; }
    code { color:#ffd45a; }
    @media (max-width: 1000px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr; } .counter-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
  </style>
</head>
<body>
  <header>
    <div class="brand"><img class="brand-icon" src="/favicon.ico?v=orthos-20260511" alt=""><h1>Orthos API Dashboard</h1></div>
    <div class="small" id="updated">Loading...</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel status-card"><div class="label">Orthos</div><div class="value" id="overall">...</div></div>
      <div class="panel status-card"><div class="label">Model</div><div class="value" id="model">...</div></div>
      <div class="panel status-card"><div class="label">Kyle Access</div><div class="value" id="gate">...</div></div>
      <div class="panel status-card"><div class="label">Queue</div><div class="value" id="queue">...</div></div>
    </section>
    <section class="panel">
      <div class="health-head">
        <div>
          <div class="label">One Button Verification</div>
          <div id="healthResult" class="health-status warn">Not run yet</div>
          <div id="healthMeta" class="small">Tests models endpoint and a tiny chat completion through Orthos.</div>
        </div>
        <button onclick="runHealthTest()">Test Orthos</button>
      </div>
      <div id="healthChecks" class="checks"></div>
    </section>
    <section class="workgrid">
      <div class="panel">
        <div class="label">Current Interface Request</div>
        <pre id="active" class="small activebox">...</pre>
      </div>
      <div class="panel">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
          <div class="label">Traffic Counters</div>
          <div class="counter-tabs">
            <button id="counter5" class="active" onclick="setCounterWindow('last_5_minutes')">5m</button>
            <button id="counter60" onclick="setCounterWindow('last_hour')">1h</button>
          </div>
        </div>
        <div id="counters" class="counter-grid"></div>
      </div>
    </section>
    <section class="grid3">
      <div class="panel"><div class="label">Current Speed</div><div class="value" id="speedNow">...</div><div class="meter"><div id="speedMeter"></div></div></div>
      <div class="panel"><div class="label">Processed Tokens</div><div class="value" id="tokensWindow">...</div></div>
      <div class="panel"><div class="label">Recent Workload</div><div class="value" id="workload">...</div></div>
    </section>
    <section class="panel">
      <div class="label">Recent Orthos Interface Traffic</div>
      <div class="table-scroll"><table><thead><tr><th>Time</th><th>Endpoint</th><th>Status</th><th>Duration</th><th>Queue</th><th>Model</th><th>Category</th></tr></thead><tbody id="metrics"></tbody></table></div>
    </section>
  </main>
  <script>
    let counterWindow = 'last_5_minutes';
    const cls = (ok, warn=false) => ok ? 'good' : (warn ? 'warn' : 'bad');
    const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const fmtTime = ts => ts ? new Date(ts * 1000).toLocaleTimeString() : '';
    function fmtDuration(ms) {
      ms = Number(ms || 0);
      if (ms < 1000) return `${ms}ms`;
      const seconds = Math.floor(ms / 1000);
      const minutes = Math.floor(seconds / 60);
      return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
    }
    async function refresh() {
      try {
        const s = await (await fetch('/api/status')).json();
        renderStatus(s);
      } catch (e) {
        document.getElementById('updated').textContent = 'Refresh failed - ' + new Date().toLocaleTimeString();
        document.getElementById('overall').innerHTML = `<span class="bad">Down</span>`;
      }
    }
    function renderStatus(s) {
      const status = s.status || 'down';
      const busy = status === 'busy';
      const blocked = status === 'blocked';
      const degraded = status === 'degraded';
      document.getElementById('updated').textContent = 'Auto-refresh every 5s - Updated ' + new Date().toLocaleTimeString();
      document.getElementById('overall').innerHTML = `<span class="${blocked ? 'bad' : (busy || degraded ? 'warn' : 'good')}">${esc(statusLabel(status))}</span>`;
      document.getElementById('model').innerHTML = `<span class="${cls(s.model?.available)}">${s.model?.available ? 'Available' : 'Unavailable'}</span><div class="small">${esc(s.model?.id || '')}</div>`;
      document.getElementById('gate').innerHTML = `<span class="${cls(s.gate?.enabled)}">${s.gate?.enabled ? 'Allowed' : 'Blocked'}</span>`;
      document.getElementById('queue').innerHTML = `<span class="${s.queue?.active ? 'warn' : 'good'}">${s.queue?.active ? 'Busy' : 'Clear'}</span><div class="small">timeout ${s.queue?.timeout_seconds || 0}s</div>`;
      document.getElementById('active').textContent = Object.keys(s.queue?.current || {}).length ? JSON.stringify(s.queue.current, null, 2) : 'No request in flight';
      renderCounters(s.traffic?.counters || {});
      renderPerf(s.performance || {});
      renderMetrics(s.traffic?.metrics || []);
    }
    function statusLabel(status) {
      return ({ready:'Ready', busy:'Busy / Queued', blocked:'Blocked', degraded:'Degraded', down:'Down'})[status] || status;
    }
    async function runHealthTest() {
      const result = document.getElementById('healthResult');
      const meta = document.getElementById('healthMeta');
      result.className = 'health-status warn';
      result.textContent = 'Testing...';
      meta.textContent = 'Running Orthos read-only test now.';
      document.getElementById('healthChecks').innerHTML = '';
      try {
        const r = await fetch('/api/test', {method:'POST'});
        const data = await r.json();
        renderHealth(data);
      } catch (e) {
        result.className = 'health-status bad';
        result.textContent = 'Test failed to run';
        meta.textContent = String(e);
      }
      refresh();
    }
    function renderHealth(data) {
      const result = document.getElementById('healthResult');
      const meta = document.getElementById('healthMeta');
      result.className = `health-status ${data.ok ? 'good' : 'bad'}`;
      result.textContent = data.ok ? 'Orthos test passed' : `${data.failed || 0} check(s) failed`;
      meta.textContent = `Completed in ${data.duration_ms || 0}ms at ${new Date((data.ts || Date.now() / 1000) * 1000).toLocaleTimeString()}`;
      document.getElementById('healthChecks').innerHTML = (data.checks || []).map(c =>
        `<div class="check ${c.ok ? 'ok' : 'fail'}"><div class="name ${c.ok ? 'good' : 'bad'}">${c.ok ? 'OK' : 'FAIL'} - ${esc(c.name)}</div><div class="detail">${esc(c.detail || '')}</div></div>`
      ).join('');
    }
    function setCounterWindow(name) {
      counterWindow = name;
      document.getElementById('counter5').classList.toggle('active', name === 'last_5_minutes');
      document.getElementById('counter60').classList.toggle('active', name === 'last_hour');
      refresh();
    }
    function counterCard(name, value, klass='') {
      return `<div class="counter-card"><div class="name">${name}</div><div class="num ${klass}">${Number(value || 0).toLocaleString()}</div></div>`;
    }
    function renderCounters(c) {
      const row = c[counterWindow] || {};
      document.getElementById('counters').innerHTML =
        counterCard('Requests', row.requests, 'blue') +
        counterCard('Success', row.success, 'good') +
        counterCard('401s', row.unauthorized, row.unauthorized ? 'warn' : '') +
        counterCard('Blocked', row.blocked, row.blocked ? 'warn' : '') +
        counterCard('Errors', (row.upstream_errors || 0) + (row.rate_limited || 0), (row.upstream_errors || row.rate_limited) ? 'bad' : '');
    }
    function renderPerf(p) {
      const latest = p.latest || {};
      const gen = latest.generate_tps || 0;
      const prompt = latest.prompt_tps || 0;
      document.getElementById('speedNow').innerHTML = latest.generated_tokens
        ? `<span class="good">${Number(gen).toFixed(1)}</span> gen t/s<br><span class="blue">${Number(prompt).toFixed(0)}</span> prompt t/s`
        : '<span class="warn">No recent generation</span>';
      document.getElementById('speedMeter').style.width = `${Math.min(100, gen / 80 * 100)}%`;
      const w = p.windows || {};
      document.getElementById('tokensWindow').innerHTML =
        `1h: <span class="blue">${(w['1h']?.tokens || 0).toLocaleString()}</span><br>` +
        `12h: <span class="blue">${(w['12h']?.tokens || 0).toLocaleString()}</span><br>` +
        `24h: <span class="blue">${(w['24h']?.tokens || 0).toLocaleString()}</span>`;
      document.getElementById('workload').innerHTML =
        `1h: ${w['1h']?.requests || 0} req<br>` +
        `avg gen: ${(w['1h']?.avg_generate_tps || 0).toFixed(1)} t/s<br>` +
        `max ctx: ${(w['1h']?.max_context || 0).toLocaleString()}`;
    }
    function renderMetrics(metrics) {
      document.getElementById('metrics').innerHTML = metrics.slice(0, 40).map(m => {
        const status = Number(m.status || 0);
        const rowClass = status === 503 || status === 429 ? 'row-blocked' : (status >= 500 ? 'row-error' : '');
        const pillClass = status === 503 ? 'status-503' : (status === 429 ? 'status-429' : (status >= 500 ? 'status-error' : (status >= 200 && status < 300 ? 'status-ok' : '')));
        const detail = m.generation
          ? `${m.generation.generated_tokens} tokens in ${m.generation.seconds}s, ${m.generation.generate_tps} T/s, context ${m.generation.context}`
          : (m.category || '');
        return `<tr class="${rowClass}"><td>${fmtTime(m.ts)}</td><td>${esc(m.method || '')} ${esc(m.path || '')}</td><td><span class="status-pill ${pillClass}">${status}</span></td><td>${fmtDuration(m.duration_ms)}</td><td>${fmtDuration(m.queue_ms)}</td><td>${esc(m.model || '')}</td><td>${esc(detail)}</td></tr>`;
      }).join('');
    }
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""


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
        except Exception:
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
            for m in models_data.get("data", [])
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
                "messages": [
                    {"role": "user", "content": "Reply exactly: dashboard ok"}
                ],
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self.send(
                HTTPStatus.OK, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8"
            )
            return
        if path == "/favicon.ico":
            icon_path = ROOT / "favicon.ico"
            if icon_path.exists():
                self.send(HTTPStatus.OK, icon_path.read_bytes(), "image/x-icon")
                return
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if path == "/api/status":
            try:
                self.send_json(status_payload())
            except Exception as exc:
                self.send_json({"status": "down", "error": str(exc), "ts": time.time()})
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path == "/api/test":
            self.send_json(health_test())
            return
        self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass


def main() -> int:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"Orthos read-only dashboard: http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"Orthos upstream: {ORTHOS_BASE_URL}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
