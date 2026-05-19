INDEX_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reaper Dashboard</title>
  <link rel="icon" href="/reaper.png" sizes="any">
  <link rel="shortcut icon" href="/reaper.png">
  <style>
    :root { color-scheme: dark; --bg:#070205; --panel:#120508; --panel2:#1a070c; --line:#3a1822; --text:#f3e6dd; --muted:#a07080; --good:#00d9a0; --bad:#ff3344; --warn:#ffaa00; --accent:#d3133b; --reaper-accent:#d3133b; --bone:#f4d4d8; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 18% -10%, rgba(211,19,59,.20), transparent 32%), radial-gradient(circle at 82% -4%, rgba(140,12,40,.14), transparent 28%), linear-gradient(180deg, #0c0306, #050103 48%, #000); color:var(--text); }
    header { padding:18px 22px; border-bottom:1px solid #4a1a26; display:flex; align-items:center; justify-content:space-between; gap:16px; background:linear-gradient(90deg, rgba(8,2,4,.98), rgba(22,6,10,.94) 55%, rgba(40,8,16,.78)); box-shadow:0 10px 30px rgba(0,0,0,.70), inset 0 -1px 0 rgba(211,19,59,.22); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .brand-icon { width:36px; height:36px; flex:0 0 auto; filter:drop-shadow(0 0 5px rgba(211,19,59,.55)) drop-shadow(0 0 14px rgba(211,19,59,.30)); animation:scythe-sway 6s infinite alternate ease-in-out; transform-origin:50% 80%; }
    @keyframes scythe-sway {
      0%   { transform:rotate(-4deg); }
      100% { transform:rotate(4deg); }
    }
    h1 { margin:0; font-size:22px; font-weight:700; color:var(--bone); text-shadow:0 0 6px rgba(211,19,59,.55), 0 0 18px rgba(140,12,40,.38), 0 0 36px rgba(80,4,18,.20); animation:reaper-pulse 5s infinite alternate ease-in-out; letter-spacing:.02em; }
    @keyframes reaper-pulse {
      0%   { color:#e8c4cc; text-shadow:0 0 5px rgba(211,19,59,.45), 0 0 15px rgba(140,12,40,.30), 0 0 30px rgba(60,4,16,.16); }
      50%  { color:#f8dde2; text-shadow:0 0 9px rgba(255,40,80,.62), 0 0 24px rgba(211,19,59,.44), 0 0 48px rgba(140,12,40,.22); }
      100% { color:#f4d4d8; text-shadow:0 0 7px rgba(211,19,59,.50), 0 0 20px rgba(140,12,40,.34), 0 0 40px rgba(60,4,16,.18); }
    }
    main { position:relative; padding:20px; display:grid; gap:16px; max-width:1320px; margin:0 auto; isolation:isolate; }
    main::before { content:""; position:absolute; inset:8px; border-radius:10px; background:radial-gradient(circle at 20% 10%, rgba(211,19,59,.08), transparent 34%), radial-gradient(circle at 80% 20%, rgba(140,12,40,.06), transparent 30%), rgba(0,0,0,.08); opacity:.78; z-index:-1; pointer-events:none; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .grid3 { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; }
    .workgrid { display:grid; grid-template-columns: minmax(260px, .9fr) minmax(520px, 1.6fr); gap:16px; align-items:stretch; }
    .panel { background:linear-gradient(180deg, #1a070c, #0a0204); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.60), inset 0 1px 0 rgba(211,19,59,.06); }
    .status-card { min-height:118px; overflow:hidden; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; margin-top:8px; line-height:1.22; overflow-wrap:anywhere; }
    .small { color:var(--muted); font-size:13px; line-height:1.45; }
    .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .blue { color:var(--accent); }
    button { border:1px solid #6a1828; background:linear-gradient(180deg, #2a060e, #110307); color:var(--bone); border-radius:6px; padding:10px 13px; cursor:pointer; font-weight:650; box-shadow:inset 0 1px 0 rgba(211,19,59,.18); }
    button:hover { background:linear-gradient(180deg, #3c0a16, #160408); border-color:var(--accent); }
    .health-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; }
    .health-status { font-size:22px; font-weight:700; margin-top:6px; }
    .checks { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; margin-top:12px; }
    .check { border:1px solid var(--line); background:#0c0306; border-radius:6px; padding:9px 10px; min-height:64px; }
    .check.ok { border-color:#00d9a0; background:#041a14; }
    .check.fail { border-color:#ff3344; background:#1d060c; }
    .check .name { font-weight:700; }
    .check .detail { margin-top:4px; font-size:12px; color:var(--muted); overflow-wrap:anywhere; }
    .activebox { min-height:118px; max-height:178px; overflow:auto; margin:8px 0 0; white-space:pre-wrap; }
    .counter-grid { display:grid; grid-template-columns: repeat(5, minmax(82px, 1fr)); gap:8px; margin-top:10px; }
    .counter-card { border:1px solid var(--line); background:#0c0306; border-radius:6px; padding:9px; min-height:64px; }
    .counter-card .num { font-size:22px; font-weight:700; margin-top:4px; }
    .counter-card .name { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    .counter-tabs { display:flex; gap:8px; }
    .counter-tabs button { border-color:var(--line); background:#0c0306; padding:6px 9px; font-size:12px; }
    .counter-tabs button.active { border-color:var(--accent); color:var(--bone); background:#1a040a; }
    .meter { height:8px; border-radius:999px; background:#070205; border:1px solid var(--line); overflow:hidden; margin-top:10px; }
    .meter > div { height:100%; background:linear-gradient(90deg, #7a0a1f, #d3133b, #ff4060); width:0%; box-shadow:0 0 14px rgba(211,19,59,.75); }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .table-scroll { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:6px; margin-top:10px; }
    .table-scroll table { min-width:760px; }
    .table-scroll thead th { position:sticky; top:0; background:var(--panel); z-index:1; }
    .status-pill { display:inline-block; min-width:42px; text-align:center; border-radius:999px; padding:2px 8px; font-weight:700; font-size:12px; border:1px solid var(--line); }
    .status-ok { background:#041a14; color:#caffeb; border-color:#00d9a0; }
    .status-503, .status-429 { background:#1d060c; color:#ffd5d8; border-color:#ff3344; }
    .status-error { background:#1a1000; color:#ffe2a8; border-color:#ffaa00; }
    tr.row-blocked td { background:rgba(255,51,68,.10); color:#ffd5d8; }
    tr.row-error td { background:rgba(255,170,0,.10); color:#ffe2a8; }
    .alert { display:none; border-radius:8px; padding:12px 14px; border:1px solid; gap:12px; align-items:flex-start; box-shadow:0 8px 24px rgba(0,0,0,.60); }
    .alert.show { display:flex; }
    .alert-down { background:linear-gradient(180deg, #220610, #0e0306); border-color:#ff3344; color:#ffd5d8; }
    .alert-warn { background:linear-gradient(180deg, #1a1000, #0d0800); border-color:#ffaa00; color:#ffe2a8; }
    .alert-icon { font-size:22px; line-height:1; flex:0 0 auto; }
    .alert-body { flex:1; min-width:0; }
    .alert-title { font-weight:700; font-size:15px; margin-bottom:3px; }
    .alert-detail { font-size:13px; opacity:.92; overflow-wrap:anywhere; }
    code { color:var(--accent); }
    @media (prefers-reduced-motion: reduce) { h1, main::before, .brand-icon { animation:none; } }
    @media (max-width: 1000px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr; } .counter-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <svg class="brand-icon" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <linearGradient id="blade-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#ff4060"/>
            <stop offset="60%" stop-color="#d3133b"/>
            <stop offset="100%" stop-color="#7a0a1f"/>
          </linearGradient>
        </defs>
        <!-- snath (handle) -->
        <line x1="7" y1="34" x2="27" y2="9" stroke="#3a1a22" stroke-width="3.6" stroke-linecap="round"/>
        <line x1="7" y1="34" x2="27" y2="9" stroke="#d3133b" stroke-width="2.0" stroke-linecap="round"/>
        <!-- blade -->
        <path d="M27 8 Q36 10 36 19 Q31 17 25 13 Q24 11 27 8 Z" fill="url(#blade-grad)" stroke="#7a0a1f" stroke-width="0.8" stroke-linejoin="round"/>
        <!-- grip nub -->
        <circle cx="7" cy="34" r="2.2" fill="#7a0a1f" stroke="#3a1a22" stroke-width="0.6"/>
      </svg>
      <h1>Reaper Dashboard</h1>
    </div>
    <div class="small" id="updated">Loading...</div>
  </header>
  <main>
    <div id="alert" class="alert">
      <div class="alert-icon" id="alertIcon">!</div>
      <div class="alert-body">
        <div class="alert-title" id="alertTitle"></div>
        <div class="alert-detail" id="alertDetail"></div>
      </div>
    </div>
    <section class="grid">
      <div class="panel status-card"><div class="label">Reaper</div><div class="value" id="overall">...</div></div>
      <div class="panel status-card"><div class="label">Model</div><div class="value" id="model">...</div></div>
      <div class="panel status-card"><div class="label">Version</div><div class="value" id="version">...</div></div>
      <div class="panel status-card"><div class="label">VRAM</div><div class="value" id="vramStatus">...</div></div>
    </section>
    <section class="panel">
      <div class="health-head">
        <div>
          <div class="label">One Button Verification</div>
          <div id="healthResult" class="health-status warn">Not run yet</div>
          <div id="healthMeta" class="small">Tests reachability, model list, and a tiny generation through Reaper.</div>
        </div>
        <button onclick="runHealthTest()">Test Reaper</button>
      </div>
      <div id="healthChecks" class="checks"></div>
    </section>
    <section class="workgrid">
      <div class="panel">
        <div class="label">Current Interface Request</div>
        <pre id="active" class="small activebox">No request in flight</pre>
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
      <div class="label">Recent Reaper Traffic</div>
      <div class="table-scroll"><table><thead><tr><th>Time</th><th>Endpoint</th><th>Status</th><th>Duration</th><th>Queue</th><th>Model</th><th>Category</th></tr></thead><tbody id="metrics"></tbody></table></div>
    </section>
  </main>
  <script>
    let counterWindow = 'last_5_minutes';
    const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const fmtTime = ts => ts ? new Date(ts * 1000).toLocaleTimeString() : '';
    function fmtDuration(ms) {
      ms = Number(ms || 0);
      if (ms < 1000) return `${ms}ms`;
      const seconds = Math.floor(ms / 1000);
      const minutes = Math.floor(seconds / 60);
      return minutes ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
    }
    function showAlert(kind, title, detail) {
      const a = document.getElementById('alert');
      a.className = 'alert show alert-' + kind;
      document.getElementById('alertIcon').textContent = kind === 'down' ? '✖' : '⚠';
      document.getElementById('alertTitle').textContent = title;
      document.getElementById('alertDetail').textContent = detail || '';
    }
    function hideAlert() {
      document.getElementById('alert').className = 'alert';
    }
    async function refresh() {
      try {
        const r = await fetch('/api/status');
        const s = await r.json();
        renderStatus(s);
      } catch(e) {
        document.getElementById('updated').textContent = 'Refresh failed - ' + new Date().toLocaleTimeString();
        document.getElementById('overall').innerHTML = '<span class="bad">Down</span>';
        showAlert('down', 'Dashboard cannot reach Reaper', 'The /api/status endpoint did not respond. The dashboard itself may be restarting, or your network connection dropped. ' + String(e));
      }
    }
    function renderStatus(s) {
      const up = s.status === 'up';
      const loaded = s.loaded || [];
      document.getElementById('updated').textContent = 'Auto-refresh every 10s - Updated ' + new Date().toLocaleTimeString();
      document.getElementById('overall').innerHTML = up ? '<span class="good">Up</span>' : '<span class="bad">Down</span>';
      if (up) {
        hideAlert();
      } else {
        const err = s.error ? (typeof s.error === 'string' ? s.error : JSON.stringify(s.error)) : 'No error detail returned.';
        const looksLikeTimeout = /timed out|timeout|refused|unreachable|econnrefused|enetunreach|no route to host/i.test(err);
        const title = looksLikeTimeout
          ? 'Ollama upstream unreachable (Master Blaster may be offline or paused)'
          : 'Reaper reports Ollama is down';
        showAlert('down', title, 'Error from upstream: ' + err + ' — The proxy and dashboard are running; traffic will resume once the inference host is reachable again.');
      }
      document.getElementById('model').innerHTML = up
        ? `<span class="${s.model?.available ? 'good' : 'bad'}">${s.model?.available ? 'Available' : 'Unavailable'}</span><div class="small">${esc(s.model?.id || '?')}</div>`
        : '<span class="bad">-</span>';
      document.getElementById('version').innerHTML = up ? `<span class="blue">${esc(s.version || '?')}</span>` : '<span class="bad">-</span>';
      document.getElementById('vramStatus').innerHTML = loaded.length > 0
        ? `<span class="warn">Active</span><div class="small">${loaded.length} model${loaded.length !== 1 ? 's' : ''} loaded</div>`
        : `<span class="good">Idle</span>`;
      const cur = s.current || {};
      document.getElementById('active').textContent = Object.keys(cur).length
        ? JSON.stringify(cur, null, 2)
        : 'No request in flight';
      renderCounters(s.traffic?.counters || {});
      renderPerf(s.performance || {});
      renderMetrics(s.traffic?.metrics || []);
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
      const latestEmbed = p.latest_embed || {};
      const gen = latest.generate_tps || 0;
      const prompt = latest.prompt_tps || 0;
      const embedTps = latestEmbed.embed_tps || 0;
      // Prefer the more recent of generation vs embed (timestamps stamped server-side).
      const genTs = latest.ts || 0;
      const embedTs = latestEmbed.ts || 0;
      let speedHtml;
      if (latest.generated_tokens && genTs >= embedTs) {
        speedHtml = `<span class="good">${Number(gen).toFixed(1)}</span> gen t/s<br><span class="blue">${Number(prompt).toFixed(0)}</span> prompt t/s`;
      } else if (latestEmbed.embed_tokens) {
        speedHtml = `<span class="blue">${Number(embedTps).toFixed(1)}</span> embed t/s<br><span class="small">${Number(latestEmbed.embed_tokens).toLocaleString()} tokens last batch</span>`;
      } else if (latest.generated_tokens) {
        speedHtml = `<span class="good">${Number(gen).toFixed(1)}</span> gen t/s<br><span class="blue">${Number(prompt).toFixed(0)}</span> prompt t/s`;
      } else {
        speedHtml = '<span class="warn">No recent activity</span>';
      }
      document.getElementById('speedNow').innerHTML = speedHtml;
      const meterPct = gen > 0 ? gen / 80 * 100 : (embedTps > 0 ? Math.min(100, embedTps / 800 * 100) : 0);
      document.getElementById('speedMeter').style.width = `${Math.min(100, meterPct)}%`;
      const w = p.windows || {};
      const tokenLine = (win) => {
        const g = win?.gen_tokens || 0;
        const e = win?.embed_tokens || 0;
        if (!g && !e) return '<span class="blue">0</span>';
        const parts = [];
        if (g) parts.push(`<span class="good">${g.toLocaleString()}</span> gen`);
        if (e) parts.push(`<span class="blue">${e.toLocaleString()}</span> embed`);
        return parts.join(' / ');
      };
      document.getElementById('tokensWindow').innerHTML =
        `1h: ${tokenLine(w['1h'])}<br>` +
        `12h: ${tokenLine(w['12h'])}<br>` +
        `24h: ${tokenLine(w['24h'])}`;
      const w1 = w['1h'] || {};
      const speedParts = [];
      if (w1.avg_generate_tps) speedParts.push(`gen ${w1.avg_generate_tps.toFixed(1)} t/s`);
      if (w1.avg_embed_tps) speedParts.push(`embed ${w1.avg_embed_tps.toFixed(1)} t/s`);
      const speedLine = speedParts.length ? speedParts.join(', ') : '0 t/s';
      document.getElementById('workload').innerHTML =
        `1h: ${w1.requests || 0} req<br>` +
        `${speedLine}<br>` +
        `max ctx: ${(w1.max_context || 0).toLocaleString()}`;
    }
    function renderMetrics(metrics) {
      document.getElementById('metrics').innerHTML = metrics.slice(0, 40).map(m => {
        const status = Number(m.status || 0);
        const rowClass = status === 503 || status === 429 ? 'row-blocked' : (status >= 500 ? 'row-error' : '');
        const pillClass = status === 503 ? 'status-503' : (status === 429 ? 'status-429' : (status >= 500 ? 'status-error' : (status >= 200 && status < 300 ? 'status-ok' : '')));
        return `<tr class="${rowClass}"><td>${fmtTime(m.ts)}</td><td>${esc(m.method || '')} ${esc(m.path || '')}</td><td><span class="status-pill ${pillClass}">${status}</span></td><td>${fmtDuration(m.duration_ms)}</td><td>${fmtDuration(m.queue_ms)}</td><td>${esc(m.model || '')}</td><td>${esc(m.category || '')}</td></tr>`;
      }).join('');
    }
    async function runHealthTest() {
      const result = document.getElementById('healthResult');
      const meta = document.getElementById('healthMeta');
      result.className = 'health-status warn';
      result.textContent = 'Testing...';
      meta.textContent = 'Running Reaper health check now.';
      document.getElementById('healthChecks').innerHTML = '';
      try {
        const r = await fetch('/api/test', {method:'POST'});
        const data = await r.json();
        renderHealth(data);
      } catch(e) {
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
      result.textContent = data.ok ? 'Reaper test passed' : `${data.failed || 0} check(s) failed`;
      meta.textContent = `Completed in ${data.duration_ms || 0}ms at ${new Date((data.ts || Date.now()/1000)*1000).toLocaleTimeString()}`;
      document.getElementById('healthChecks').innerHTML = (data.checks || []).map(c =>
        `<div class="check ${c.ok ? 'ok' : 'fail'}"><div class="name ${c.ok ? 'good' : 'bad'}">${c.ok ? 'OK' : 'FAIL'} - ${esc(c.name)}</div><div class="detail">${esc(c.detail || '')}</div></div>`
      ).join('');
    }
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>""".encode("utf-8")
