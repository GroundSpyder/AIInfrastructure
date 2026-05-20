INDEX_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Fleet Dashboard</title>
  <link rel="icon" href="/fleet.png" sizes="any">
  <link rel="shortcut icon" href="/fleet.png">
  <style>
    :root { color-scheme: dark; --bg:#040104; --panel:#0a0205; --panel2:#100406; --line:#2a1018; --text:#ece0d8; --muted:#90606c; --good:#00d9a0; --bad:#ff3344; --warn:#ffaa00; --bone:#ecdfe1;
      /* Default theme is Reaper (red). Per-backend body[data-backend="..."] overrides below swap these. */
      --accent:#d3133b; --accent-deep:#7a0a1f; --accent-light:#ff4060;
    }
    body[data-backend="reaper"]  { --accent:#d3133b; --accent-deep:#7a0a1f; --accent-light:#ff4060; }
    body[data-backend="lilblue"] { --accent:#1a9fff; --accent-deep:#0a5a9f; --accent-light:#4db8ff; }
    /* OBD = "Blackflame" — violet/purple. Distinct from red+blue, hints at the mystical/death theme. */
    body[data-backend="obd"]     { --accent:#9d4edd; --accent-deep:#5c2585; --accent-light:#c97ef5; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 18% -10%, color-mix(in srgb, var(--accent) 14%, transparent), transparent 30%), radial-gradient(circle at 82% -4%, color-mix(in srgb, var(--accent-deep) 12%, transparent), transparent 26%), linear-gradient(180deg, #060204, #020102 48%, #000); color:var(--text); transition:background-color .35s ease; }
    header { padding:18px 22px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:16px; background:linear-gradient(90deg, rgba(4,1,3,.98), rgba(12,3,6,.94) 55%, rgba(22,5,10,.74)); box-shadow:0 10px 30px rgba(0,0,0,.80), inset 0 -1px 0 color-mix(in srgb, var(--accent) 22%, transparent); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .brand-icon { width:36px; height:36px; flex:0 0 auto; color:var(--accent); filter:drop-shadow(0 0 5px color-mix(in srgb, var(--accent) 55%, transparent)) drop-shadow(0 0 14px color-mix(in srgb, var(--accent) 30%, transparent)); animation:scythe-sway 6s infinite alternate ease-in-out; transform-origin:50% 80%; transition:color .35s ease, filter .35s ease; }
    .brand-icon .blade-light { stop-color:var(--accent-light); }
    .brand-icon .blade-mid   { stop-color:var(--accent); }
    .brand-icon .blade-deep  { stop-color:var(--accent-deep); }
    .brand-icon .snath       { stroke:var(--accent); }
    .brand-icon .snath-shadow{ stroke:#3a1a22; }
    .brand-icon .blade-stroke{ stroke:var(--accent-deep); }
    .brand-icon .grip-fill   { fill:var(--accent-deep); }
    @keyframes scythe-sway {
      0%   { transform:rotate(-4deg); }
      100% { transform:rotate(4deg); }
    }
    h1 { margin:0; font-size:22px; font-weight:700; color:var(--bone); text-shadow:0 0 5px color-mix(in srgb, var(--accent) 42%, transparent), 0 0 15px color-mix(in srgb, var(--accent-deep) 30%, transparent), 0 0 30px color-mix(in srgb, var(--accent-deep) 15%, transparent); animation:title-pulse 5s infinite alternate ease-in-out; letter-spacing:.02em; transition:color .35s ease, text-shadow .35s ease; }
    @keyframes title-pulse {
      0%   { opacity:.86; }
      50%  { opacity:1; }
      100% { opacity:.92; }
    }
    nav.tabs { display:flex; gap:0; padding:0 22px; background:linear-gradient(180deg, rgba(8,2,4,.92), rgba(2,1,2,.98)); border-bottom:1px solid var(--line); }
    nav.tabs button { background:transparent; border:none; border-bottom:2px solid transparent; color:var(--muted); padding:14px 22px; font-size:14px; font-weight:700; letter-spacing:.10em; text-transform:uppercase; cursor:pointer; transition:color .15s, border-color .15s; }
    nav.tabs button:hover { color:var(--bone); }
    /* The accent for an inactive tab is fixed to that backend's color so the
       tabs themselves act as a color legend — REAPER stays red, LILBLUE stays
       blue, OBD stays purple regardless of which is active. */
    nav.tabs button[data-backend="reaper"]  { --tab-color:#d3133b; }
    nav.tabs button[data-backend="lilblue"] { --tab-color:#1a9fff; }
    nav.tabs button[data-backend="obd"]     { --tab-color:#9d4edd; }
    nav.tabs button.active { color:var(--tab-color); border-bottom-color:var(--tab-color); text-shadow:0 0 8px color-mix(in srgb, var(--tab-color) 55%, transparent); }
    nav.tabs .target-url { margin-left:auto; align-self:center; color:var(--muted); font-size:12px; font-family:Consolas, monospace; }
    main { position:relative; padding:20px; display:grid; gap:16px; max-width:1320px; margin:0 auto; isolation:isolate; }
    main::before { content:""; position:absolute; inset:8px; border-radius:10px; background:radial-gradient(circle at 20% 10%, color-mix(in srgb, var(--accent) 6%, transparent), transparent 30%), radial-gradient(circle at 80% 20%, color-mix(in srgb, var(--accent-deep) 5%, transparent), transparent 28%), rgba(0,0,0,.12); opacity:.82; z-index:-1; pointer-events:none; transition:background .35s ease; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .grid3 { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; }
    .workgrid { display:grid; grid-template-columns: minmax(260px, .9fr) minmax(520px, 1.6fr); gap:16px; align-items:stretch; }
    .panel { background:linear-gradient(180deg, #0c0306, #040102); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.70), inset 0 1px 0 color-mix(in srgb, var(--accent) 6%, transparent); transition:box-shadow .35s ease; }
    .status-card { min-height:118px; overflow:hidden; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; margin-top:8px; line-height:1.22; overflow-wrap:anywhere; }
    .small { color:var(--muted); font-size:13px; line-height:1.45; }
    .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .blue { color:var(--accent); }
    button.action { border:1px solid color-mix(in srgb, var(--accent) 40%, #1a070a); background:linear-gradient(180deg, #14050a, #060103); color:var(--bone); border-radius:6px; padding:10px 13px; cursor:pointer; font-weight:650; box-shadow:inset 0 1px 0 color-mix(in srgb, var(--accent) 15%, transparent); transition:border-color .15s, background .15s; }
    button.action:hover { background:linear-gradient(180deg, #260712, #0c0205); border-color:var(--accent); }
    button.action:disabled { opacity:.5; cursor:not-allowed; }
    .health-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; }
    .health-status { font-size:22px; font-weight:700; margin-top:6px; }
    .checks { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; margin-top:12px; }
    .check { border:1px solid var(--line); background:#060203; border-radius:6px; padding:9px 10px; min-height:64px; }
    .check.ok { border-color:#00d9a0; background:#041a14; }
    .check.fail { border-color:#ff3344; background:#140408; }
    .check .name { font-weight:700; }
    .check .detail { margin-top:4px; font-size:12px; color:var(--muted); overflow-wrap:anywhere; }
    .activebox { min-height:64px; max-height:178px; overflow:auto; margin:8px 0 0; white-space:pre-wrap; font-family:Consolas, monospace; font-size:13px; }
    .counter-grid { display:grid; grid-template-columns: repeat(5, minmax(82px, 1fr)); gap:8px; margin-top:10px; }
    .counter-card { border:1px solid var(--line); background:#060203; border-radius:6px; padding:9px; min-height:64px; }
    .counter-card .num { font-size:22px; font-weight:700; margin-top:4px; }
    .counter-card .name { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    .counter-tabs { display:flex; gap:8px; margin-top:10px; }
    .counter-tabs button { border:1px solid var(--line); background:#060203; padding:6px 9px; font-size:12px; color:var(--text); border-radius:6px; cursor:pointer; }
    .counter-tabs button.active { border-color:var(--accent); color:var(--bone); background:color-mix(in srgb, var(--accent) 12%, #10030a); }
    .meter { height:8px; border-radius:999px; background:#040104; border:1px solid var(--line); overflow:hidden; margin-top:10px; }
    .meter > div { height:100%; background:linear-gradient(90deg, var(--accent-deep), var(--accent), var(--accent-light)); width:0%; box-shadow:0 0 12px color-mix(in srgb, var(--accent) 60%, transparent); transition:width .25s ease, background .35s ease; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .table-scroll { max-height:420px; overflow:auto; border:1px solid var(--line); border-radius:6px; margin-top:10px; }
    .table-scroll table { min-width:760px; }
    .table-scroll thead th { position:sticky; top:0; background:var(--panel); z-index:1; }
    .status-pill { display:inline-block; min-width:42px; text-align:center; border-radius:999px; padding:2px 8px; font-weight:700; font-size:12px; border:1px solid var(--line); }
    .status-ok { background:#041a14; color:#caffeb; border-color:#00d9a0; }
    .status-503, .status-429 { background:#140408; color:#ffd5d8; border-color:#ff3344; }
    .status-error { background:#1a1000; color:#ffe2a8; border-color:#ffaa00; }
    tr.row-blocked td { background:rgba(255,51,68,.10); color:#ffd5d8; }
    tr.row-error td { background:rgba(255,170,0,.10); color:#ffe2a8; }
    .alert { display:none; border-radius:8px; padding:12px 14px; border:1px solid; gap:12px; align-items:flex-start; box-shadow:0 8px 24px rgba(0,0,0,.60); }
    .alert.show { display:flex; }
    /* DOWN alert stays red (semantic) — not themed per backend. */
    .alert-down { background:linear-gradient(180deg, #18040a, #080204); border-color:#ff3344; color:#ffd5d8; }
    .alert-warn { background:linear-gradient(180deg, #1a1000, #0d0800); border-color:#ffaa00; color:#ffe2a8; }
    .alert-icon { font-size:22px; line-height:1; flex:0 0 auto; }
    .alert-body { flex:1; min-width:0; }
    .alert-title { font-weight:700; font-size:15px; margin-bottom:3px; }
    .alert-detail { font-size:13px; opacity:.92; overflow-wrap:anywhere; }
    code { color:var(--accent); }
    /* Per-backend element visibility. The "counters" + "perf" sections only
       exist on LilBlue/Reaper (proxies with internal trackers). OBD has a
       different upstream metric shape, so its tab hides them.
       The traffic table itself works for all three. */
    body[data-backend="obd"] [data-counters-only],
    body[data-backend="obd"] [data-perf-only] { display:none; }
    /* If a backend has no traffic at all (LilBlue/Reaper before any
       requests), the table is empty; we render an empty-state row from JS. */
    @media (prefers-reduced-motion: reduce) { h1, main::before, .brand-icon { animation:none; } }
    @media (max-width: 1000px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr; } .counter-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } nav.tabs { padding:0 10px; overflow-x:auto; } nav.tabs button { padding:14px 12px; } nav.tabs .target-url { display:none; } }
  </style>
</head>
<body data-backend="reaper">
  <header>
    <div class="brand">
      <svg class="brand-icon" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <linearGradient id="blade-grad" x1="0" y1="0" x2="1" y2="1">
            <stop class="blade-light" offset="0%"/>
            <stop class="blade-mid"   offset="60%"/>
            <stop class="blade-deep"  offset="100%"/>
          </linearGradient>
        </defs>
        <line class="snath-shadow" x1="7" y1="34" x2="27" y2="9" stroke-width="3.6" stroke-linecap="round"/>
        <line class="snath"        x1="7" y1="34" x2="27" y2="9" stroke-width="2.0" stroke-linecap="round"/>
        <path class="blade-stroke" d="M27 8 Q36 10 36 19 Q31 17 25 13 Q24 11 27 8 Z" fill="url(#blade-grad)" stroke-width="0.8" stroke-linejoin="round"/>
        <circle class="grip-fill" cx="7" cy="34" r="2.2" stroke="#3a1a22" stroke-width="0.6"/>
      </svg>
      <h1>AI Fleet Dashboard</h1>
    </div>
    <div class="small" id="updated">Loading...</div>
  </header>
  <nav class="tabs" id="tabs">
    <button data-backend="reaper" class="active">REAPER</button>
    <button data-backend="lilblue">LILBLUE</button>
    <button data-backend="obd">OBD</button>
    <span class="target-url" id="targetUrl"></span>
  </nav>
  <main>
    <div id="alert" class="alert">
      <div class="alert-icon" id="alertIcon">!</div>
      <div class="alert-body">
        <div class="alert-title" id="alertTitle"></div>
        <div class="alert-detail" id="alertDetail"></div>
      </div>
    </div>
    <div class="grid">
      <div class="panel status-card"><div class="label">Backend</div><div class="value" id="overall">...</div></div>
      <div class="panel status-card"><div class="label">Upstream</div><div class="value" id="upstream">...</div></div>
      <div class="panel status-card"><div class="label">Model</div><div class="value" id="model">...</div></div>
      <div class="panel status-card"><div class="label">Last Updated</div><div class="value small" id="updatedAt">...</div></div>
    </div>
    <div class="workgrid">
      <div class="panel">
        <div class="health-head">
          <div>
            <div class="label">Health</div>
            <div class="health-status" id="healthStatus">Idle</div>
            <div id="healthMeta" class="small">Tests reachability, model list, and a tiny generation through the selected backend.</div>
          </div>
          <button class="action" id="testBtn" onclick="runHealthTest()">Run Test</button>
        </div>
        <div class="checks" id="checks"></div>
      </div>
      <div class="panel">
        <div class="label">In Flight</div>
        <div class="activebox" id="active">idle</div>
        <div data-counters-only>
          <div class="counter-tabs">
            <button class="active" data-window="last_5_minutes" onclick="setCounterWindow(this)">5 min</button>
            <button data-window="last_hour" onclick="setCounterWindow(this)">1 hour</button>
          </div>
          <div class="counter-grid" id="counters"></div>
        </div>
      </div>
    </div>
    <div class="panel" data-perf-only>
      <div class="label">Performance</div>
      <div class="grid3" style="margin-top:10px">
        <div class="panel" style="border-color:var(--line)"><div class="label">Latest Chat</div><div class="value" id="perfLatestChat">--</div></div>
        <div class="panel" style="border-color:var(--line)"><div class="label">Latest Embed</div><div class="value" id="perfLatestEmbed">--</div></div>
        <div class="panel" style="border-color:var(--line)"><div class="label">Window (1h / 12h / 24h)</div><div class="value small" id="perfWindows">--</div></div>
      </div>
    </div>
    <div class="panel">
      <div class="label">Recent Traffic</div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th>Duration</th><th>Model</th><th>Generation</th></tr></thead>
          <tbody id="trafficBody"></tbody>
        </table>
      </div>
    </div>
  </main>
  <script>
  const BACKENDS = ['reaper','lilblue','obd'];
  const BACKEND_PUBLIC_URL = {
    reaper:  'https://reaper.birdmug.com',
    lilblue: 'https://lilblue.birdmug.com',
    obd:     'https://obd.birdmug.com',
  };
  const BACKEND_UPSTREAM = {
    reaper:  'Master Blaster (RX 9070 XT, ROCm)',
    lilblue: 'Kaydanski (RX 6600, Vulkan)',
    obd:     'Orthos / Chris\\'s 3090 (TabbyAPI)',
  };
  let currentBackend = (() => {
    const fromHash = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (BACKENDS.includes(fromHash)) return fromHash;
    if (fromHash) console.warn('AI Fleet: unknown hash backend ' + JSON.stringify(fromHash) + '; falling back.');
    const stored = (localStorage.getItem('aiFleetBackend') || '').toLowerCase();
    if (BACKENDS.includes(stored)) return stored;
    return 'reaper';
  })();
  let counterWindow = 'last_5_minutes';
  let pollTimer = null;

  function setActiveTab(name) {
    if (!BACKENDS.includes(name)) name = 'reaper';
    currentBackend = name;
    localStorage.setItem('aiFleetBackend', name);
    history.replaceState(null, '', '#' + name);
    document.body.setAttribute('data-backend', name);
    document.querySelectorAll('#tabs button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.backend === name);
    });
    document.getElementById('targetUrl').textContent = BACKEND_PUBLIC_URL[name] || '';
    // Reset displayed data immediately so the user doesn't see stale numbers
    document.getElementById('overall').textContent = 'Loading ' + name + '...';
    document.getElementById('upstream').textContent = BACKEND_UPSTREAM[name] || '...';
    document.getElementById('model').textContent = '...';
    document.getElementById('trafficBody').innerHTML = '';
    document.getElementById('counters').innerHTML = '';
    document.getElementById('active').textContent = 'idle';
    document.getElementById('checks').innerHTML = '';
    document.getElementById('perfLatestChat').textContent = '--';
    document.getElementById('perfLatestEmbed').textContent = '--';
    document.getElementById('perfWindows').textContent = '--';
    refresh();
  }

  document.querySelectorAll('#tabs button').forEach(btn => {
    btn.addEventListener('click', () => setActiveTab(btn.dataset.backend));
  });

  function showAlert(kind, title, detail) {
    const el = document.getElementById('alert');
    el.classList.remove('alert-down','alert-warn');
    el.classList.add(kind === 'warn' ? 'alert-warn' : 'alert-down');
    document.getElementById('alertIcon').textContent = kind === 'warn' ? '!' : 'X';
    document.getElementById('alertTitle').textContent = title || '';
    document.getElementById('alertDetail').textContent = detail || '';
    el.classList.add('show');
  }
  function hideAlert() {
    document.getElementById('alert').classList.remove('show');
  }

  async function refresh() {
    const backend = currentBackend;
    try {
      const r = await fetch('/api/status?backend=' + encodeURIComponent(backend), { credentials:'same-origin', cache:'no-store' });
      let data;
      try { data = await r.json(); } catch (_) { data = { status:'down', error:'invalid JSON from upstream' }; }
      if (backend !== currentBackend) return;  // tab switched mid-flight, drop result

      const isUp = isBackendUp(data, r.status);
      if (!isUp) {
        showAlert('down', backend.toUpperCase() + ' is reporting down', data.error || data.detail || ('HTTP ' + r.status));
      } else {
        hideAlert();
      }
      render(backend, data);
    } catch (e) {
      if (backend !== currentBackend) return;
      showAlert('down', 'Cannot reach AI Fleet Dashboard backend', String(e));
    }
  }

  function isBackendUp(d, httpStatus) {
    if (httpStatus >= 500) return false;
    // LilBlue/Reaper use status:"up". OBD uses status:"ready". Both mean healthy.
    return (d.status === 'up' || d.status === 'ready');
  }

  function render(backend, d) {
    document.getElementById('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    document.getElementById('updatedAt').textContent = d.ts ? new Date(d.ts * 1000).toLocaleString() : '--';

    const overall = document.getElementById('overall');
    if (isBackendUp(d, 200)) {
      const label = d.status === 'ready' ? 'READY' : 'UP';
      overall.innerHTML = '<span class="good">' + label + '</span>' + (d.version ? ' <span class="small">' + d.version + '</span>' : '');
    } else {
      overall.innerHTML = '<span class="bad">DOWN</span>';
    }
    document.getElementById('upstream').textContent = BACKEND_UPSTREAM[backend] || '--';

    // Model row works the same for all three: d.model.id + d.model.available.
    const modelInfo = (d.model && (d.model.id || d.model.name)) || '--';
    const modelAvail = d.model && d.model.available;
    document.getElementById('model').innerHTML = modelInfo + (modelInfo === '--' ? '' :
      ' <span class="small ' + (modelAvail ? 'good' : 'bad') + '">' + (modelAvail ? 'available' : 'missing') + '</span>');

    renderInFlight(backend, d);
    renderTraffic(backend, d);
    if (d.traffic && d.traffic.counters) renderCounters(d);
    if (d.performance) renderPerf(d);
  }

  function renderInFlight(backend, d) {
    // LilBlue/Reaper put it at d.current; OBD puts it at d.queue.current.
    const current = (d.queue && d.queue.current) || d.current || {};
    const active = document.getElementById('active');
    if (current.method) {
      // Guard `started` against non-epoch-seconds upstreams. OBD's TabbyAPI
      // origin is outside our codebase, so we don't assume the unit. Only
      // render the age if `started` looks like a plausible Unix epoch seconds
      // value (between 2001-09-09 and 5138-11-16).
      const started = current.started;
      const validEpoch = typeof started === 'number' && started > 1e9 && started < 1e11;
      const ageStr = validEpoch ? ' started ' + Math.round((Date.now()/1000) - started) + 's ago' : '';
      active.textContent = current.method + ' ' + (current.path || '') + ' (' + (current.model || '?') + ')' + ageStr;
    } else if (backend === 'obd' && d.queue && d.queue.active === false) {
      active.textContent = 'idle (queue empty, gate ' + (d.gate && d.gate.enabled ? 'enabled' : 'open') + ')';
    } else {
      active.textContent = 'idle';
    }
  }

  function renderCounters(d) {
    const t = d.traffic || {};
    const counters = (t.counters && t.counters[counterWindow]) || {};
    const cBlock = document.getElementById('counters');
    const ents = [
      ['Requests', counters.requests || 0, ''],
      ['OK', counters.success || 0, 'good'],
      ['Auth Fail', counters.unauthorized || 0, 'warn'],
      ['Rate Ltd', counters.rate_limited || 0, 'warn'],
      ['Errors', counters.upstream_errors || 0, 'bad'],
    ];
    cBlock.innerHTML = ents.map(([n,v,cls]) =>
      '<div class="counter-card"><div class="name">' + n + '</div><div class="num ' + cls + '">' + v + '</div></div>'
    ).join('');
  }

  function renderTraffic(backend, d) {
    const metrics = (d.traffic && d.traffic.metrics) || [];
    const body = document.getElementById('trafficBody');
    if (!metrics.length) {
      body.innerHTML = '<tr><td colspan="7" class="small" style="text-align:center;padding:20px">No recent traffic.</td></tr>';
      return;
    }
    const rows = metrics.slice(0, 40).map(m => {
      const sec = m.duration_ms ? (m.duration_ms / 1000).toFixed(2) + 's' : '--';
      const pillCls = m.status >= 200 && m.status < 300 ? 'status-ok'
                   : m.status === 503 || m.status === 429 ? 'status-503'
                   : 'status-error';
      // OBD has m.category ("ok"/"blocked"/etc.) but no token-throughput string;
      // LilBlue/Reaper compose a "N tokens in Xs" string into category. Either renders fine.
      const generation = m.category || '';
      return '<tr><td class="small">' + new Date(m.ts * 1000).toLocaleTimeString() + '</td>'
           + '<td>' + (m.method || '') + '</td>'
           + '<td>' + (m.path || '') + '</td>'
           + '<td><span class="status-pill ' + pillCls + '">' + m.status + '</span></td>'
           + '<td>' + sec + '</td>'
           + '<td>' + (m.model || '') + '</td>'
           + '<td class="small">' + generation + '</td></tr>';
    }).join('');
    body.innerHTML = rows;
  }

  function renderPerf(d) {
    const perf = d.performance || {};
    const latest = perf.latest || {};
    const latestEmbed = perf.latest_embed || {};
    document.getElementById('perfLatestChat').textContent = latest.generate_tps
      ? latest.generate_tps + ' tok/s (' + (latest.generated_tokens || 0) + ' tok)'
      : '--';
    document.getElementById('perfLatestEmbed').textContent = latestEmbed.embed_tps
      ? latestEmbed.embed_tps + ' tok/s (' + (latestEmbed.embed_tokens || 0) + ' tok)'
      : '--';
    const w = perf.windows || {};
    document.getElementById('perfWindows').textContent =
      ['1h', '12h', '24h'].map(k => {
        const ww = w[k] || {};
        return k + ': ' + (ww.tokens || 0) + ' tok / ' + (ww.requests || 0) + ' req';
      }).join('  |  ');
  }

  function renderChecks(d) {
    const checks = d.checks || [];
    document.getElementById('checks').innerHTML = checks.map(c =>
      '<div class="check ' + (c.ok ? 'ok' : 'fail') + '"><div class="name">' + (c.name || '') + '</div><div class="detail">' + (c.detail || '') + '</div></div>'
    ).join('');
    if (typeof d.ok !== 'undefined') {
      document.getElementById('healthStatus').innerHTML = d.ok ? '<span class="good">All checks passed</span>' : '<span class="bad">' + (d.failed || 0) + ' check(s) failed</span>';
    }
  }

  async function runHealthTest() {
    const backend = currentBackend;
    const btn = document.getElementById('testBtn');
    btn.disabled = true;
    document.getElementById('healthStatus').textContent = 'Running...';
    document.getElementById('healthMeta').textContent = 'Running ' + backend.toUpperCase() + ' health check now.';
    document.getElementById('checks').innerHTML = '';
    try {
      const r = await fetch('/api/test?backend=' + encodeURIComponent(backend), { method:'POST', credentials:'same-origin', cache:'no-store' });
      const data = await r.json();
      if (backend !== currentBackend) return;
      renderChecks(data);
      document.getElementById('healthMeta').textContent = data.duration_ms ? ('Took ' + data.duration_ms + 'ms.') : '';
    } catch (e) {
      if (backend !== currentBackend) return;
      document.getElementById('healthStatus').innerHTML = '<span class="bad">Test failed</span>';
      document.getElementById('healthMeta').textContent = String(e);
    } finally {
      // Only re-enable if the user is still on the tab that initiated the
      // test. If they tab-switched mid-flight, setActiveTab() owns the
      // button state for the new tab and we shouldn't clobber it.
      if (backend === currentBackend) btn.disabled = false;
    }
  }

  function setCounterWindow(btn) {
    counterWindow = btn.dataset.window;
    document.querySelectorAll('.counter-tabs button').forEach(b => b.classList.toggle('active', b === btn));
    refresh();
  }

  setActiveTab(currentBackend);
  pollTimer = setInterval(refresh, 10000);
  window.addEventListener('hashchange', () => {
    const h = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (BACKENDS.includes(h) && h !== currentBackend) setActiveTab(h);
    else if (h && !BACKENDS.includes(h)) console.warn('AI Fleet: unknown hash backend ' + JSON.stringify(h) + '; ignoring.');
  });
  </script>
</body>
</html>
""".encode("utf-8")
