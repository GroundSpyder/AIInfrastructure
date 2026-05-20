INDEX_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Fleet Dashboard</title>
  <link rel="icon" href="/fleet.png" sizes="any">
  <link rel="shortcut icon" href="/fleet.png">
  <style>
    :root { color-scheme: dark; --bg:#040104; --panel:#0a0205; --panel2:#100406; --line:#2a1018; --text:#ece0d8; --muted:#90606c; --good:#00d9a0; --bad:#ff3344; --warn:#ffaa00; --accent:#d3133b; --bone:#ecdfe1; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 18% -10%, rgba(211,19,59,.10), transparent 30%), radial-gradient(circle at 82% -4%, rgba(140,12,40,.06), transparent 26%), linear-gradient(180deg, #060204, #020102 48%, #000); color:var(--text); }
    header { padding:18px 22px; border-bottom:1px solid #2a1018; display:flex; align-items:center; justify-content:space-between; gap:16px; background:linear-gradient(90deg, rgba(4,1,3,.98), rgba(12,3,6,.94) 55%, rgba(22,5,10,.74)); box-shadow:0 10px 30px rgba(0,0,0,.80), inset 0 -1px 0 rgba(211,19,59,.18); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    .brand-icon { width:36px; height:36px; flex:0 0 auto; filter:drop-shadow(0 0 5px rgba(211,19,59,.55)) drop-shadow(0 0 14px rgba(211,19,59,.30)); animation:scythe-sway 6s infinite alternate ease-in-out; transform-origin:50% 80%; }
    @keyframes scythe-sway {
      0%   { transform:rotate(-4deg); }
      100% { transform:rotate(4deg); }
    }
    h1 { margin:0; font-size:22px; font-weight:700; color:var(--bone); text-shadow:0 0 5px rgba(211,19,59,.42), 0 0 15px rgba(140,12,40,.24), 0 0 30px rgba(80,4,18,.12); animation:reaper-pulse 5s infinite alternate ease-in-out; letter-spacing:.02em; }
    @keyframes reaper-pulse {
      0%   { color:#d8c0c5; text-shadow:0 0 4px rgba(211,19,59,.32), 0 0 12px rgba(140,12,40,.20), 0 0 24px rgba(60,4,16,.10); }
      50%  { color:#ecdadd; text-shadow:0 0 7px rgba(255,40,80,.45), 0 0 20px rgba(211,19,59,.32), 0 0 40px rgba(140,12,40,.16); }
      100% { color:#ecdfe1; text-shadow:0 0 5px rgba(211,19,59,.36), 0 0 16px rgba(140,12,40,.22), 0 0 32px rgba(60,4,16,.12); }
    }
    nav.tabs { display:flex; gap:0; padding:0 22px; background:linear-gradient(180deg, rgba(8,2,4,.92), rgba(2,1,2,.98)); border-bottom:1px solid var(--line); }
    nav.tabs button { background:transparent; border:none; border-bottom:2px solid transparent; color:var(--muted); padding:14px 22px; font-size:14px; font-weight:700; letter-spacing:.10em; text-transform:uppercase; cursor:pointer; transition:color .15s, border-color .15s; }
    nav.tabs button:hover { color:var(--bone); }
    nav.tabs button.active { color:var(--accent); border-bottom-color:var(--accent); text-shadow:0 0 8px rgba(211,19,59,.55); }
    nav.tabs .target-url { margin-left:auto; align-self:center; color:var(--muted); font-size:12px; font-family:Consolas, monospace; }
    main { position:relative; padding:20px; display:grid; gap:16px; max-width:1320px; margin:0 auto; isolation:isolate; }
    main::before { content:""; position:absolute; inset:8px; border-radius:10px; background:radial-gradient(circle at 20% 10%, rgba(211,19,59,.04), transparent 30%), radial-gradient(circle at 80% 20%, rgba(140,12,40,.03), transparent 28%), rgba(0,0,0,.12); opacity:.82; z-index:-1; pointer-events:none; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .grid3 { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; }
    .workgrid { display:grid; grid-template-columns: minmax(260px, .9fr) minmax(520px, 1.6fr); gap:16px; align-items:stretch; }
    .panel { background:linear-gradient(180deg, #0c0306, #040102); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.70), inset 0 1px 0 rgba(211,19,59,.04); }
    .status-card { min-height:118px; overflow:hidden; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; margin-top:8px; line-height:1.22; overflow-wrap:anywhere; }
    .small { color:var(--muted); font-size:13px; line-height:1.45; }
    .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .blue { color:var(--accent); }
    button.action { border:1px solid #4a1018; background:linear-gradient(180deg, #14050a, #060103); color:var(--bone); border-radius:6px; padding:10px 13px; cursor:pointer; font-weight:650; box-shadow:inset 0 1px 0 rgba(211,19,59,.12); }
    button.action:hover { background:linear-gradient(180deg, #260712, #0c0205); border-color:var(--accent); }
    .health-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; }
    .health-status { font-size:22px; font-weight:700; margin-top:6px; }
    .checks { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; margin-top:12px; }
    .check { border:1px solid var(--line); background:#060203; border-radius:6px; padding:9px 10px; min-height:64px; }
    .check.ok { border-color:#00d9a0; background:#041a14; }
    .check.fail { border-color:#ff3344; background:#140408; }
    .check .name { font-weight:700; }
    .check .detail { margin-top:4px; font-size:12px; color:var(--muted); overflow-wrap:anywhere; }
    .activebox { min-height:118px; max-height:178px; overflow:auto; margin:8px 0 0; white-space:pre-wrap; }
    .counter-grid { display:grid; grid-template-columns: repeat(5, minmax(82px, 1fr)); gap:8px; margin-top:10px; }
    .counter-card { border:1px solid var(--line); background:#060203; border-radius:6px; padding:9px; min-height:64px; }
    .counter-card .num { font-size:22px; font-weight:700; margin-top:4px; }
    .counter-card .name { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
    .counter-tabs { display:flex; gap:8px; }
    .counter-tabs button { border-color:var(--line); background:#060203; padding:6px 9px; font-size:12px; color:var(--text); border:1px solid var(--line); border-radius:6px; cursor:pointer; }
    .counter-tabs button.active { border-color:var(--accent); color:var(--bone); background:#10030a; }
    .meter { height:8px; border-radius:999px; background:#040104; border:1px solid var(--line); overflow:hidden; margin-top:10px; }
    .meter > div { height:100%; background:linear-gradient(90deg, #4a060f, #b81030, #d3133b); width:0%; box-shadow:0 0 12px rgba(211,19,59,.60); }
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
    .alert-down { background:linear-gradient(180deg, #18040a, #080204); border-color:#ff3344; color:#ffd5d8; }
    .alert-warn { background:linear-gradient(180deg, #1a1000, #0d0800); border-color:#ffaa00; color:#ffe2a8; }
    .alert-icon { font-size:22px; line-height:1; flex:0 0 auto; }
    .alert-body { flex:1; min-width:0; }
    .alert-title { font-weight:700; font-size:15px; margin-bottom:3px; }
    .alert-detail { font-size:13px; opacity:.92; overflow-wrap:anywhere; }
    code { color:var(--accent); }
    [data-tracker-only] { display:block; }
    body[data-backend="obd"] [data-tracker-only] { display:none; }
    @media (prefers-reduced-motion: reduce) { h1, main::before, .brand-icon { animation:none; } }
    @media (max-width: 1000px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr; } .counter-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } nav.tabs { padding:0 10px; overflow-x:auto; } nav.tabs button { padding:14px 12px; } nav.tabs .target-url { display:none; } }
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
        <line x1="7" y1="34" x2="27" y2="9" stroke="#3a1a22" stroke-width="3.6" stroke-linecap="round"/>
        <line x1="7" y1="34" x2="27" y2="9" stroke="#d3133b" stroke-width="2.0" stroke-linecap="round"/>
        <path d="M27 8 Q36 10 36 19 Q31 17 25 13 Q24 11 27 8 Z" fill="url(#blade-grad)" stroke="#7a0a1f" stroke-width="0.8" stroke-linejoin="round"/>
        <circle cx="7" cy="34" r="2.2" fill="#7a0a1f" stroke="#3a1a22" stroke-width="0.6"/>
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
      <div class="panel" data-tracker-only>
        <div class="label">In Flight</div>
        <div class="activebox" id="active">idle</div>
        <div class="counter-tabs" style="margin-top:10px">
          <button class="active" data-window="last_5_minutes" onclick="setCounterWindow(this)">5 min</button>
          <button data-window="last_hour" onclick="setCounterWindow(this)">1 hour</button>
        </div>
        <div class="counter-grid" id="counters"></div>
      </div>
    </div>
    <div class="panel" data-tracker-only>
      <div class="label">Performance</div>
      <div class="grid3" style="margin-top:10px">
        <div class="panel" style="border-color:var(--line)"><div class="label">Latest Chat</div><div class="value" id="perfLatestChat">--</div></div>
        <div class="panel" style="border-color:var(--line)"><div class="label">Latest Embed</div><div class="value" id="perfLatestEmbed">--</div></div>
        <div class="panel" style="border-color:var(--line)"><div class="label">Window (1h / 12h / 24h)</div><div class="value small" id="perfWindows">--</div></div>
      </div>
    </div>
    <div class="panel" data-tracker-only>
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
  let currentBackend = (() => {
    const fromHash = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (BACKENDS.includes(fromHash)) return fromHash;
    const stored = (localStorage.getItem('aiFleetBackend') || '').toLowerCase();
    if (BACKENDS.includes(stored)) return stored;
    return 'reaper';
  })();
  let counterWindow = 'last_5_minutes';
  let pollTimer = null;

  function setActiveTab(name) {
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
    document.getElementById('upstream').textContent = '...';
    document.getElementById('model').textContent = '...';
    document.getElementById('trafficBody').innerHTML = '';
    document.getElementById('counters').innerHTML = '';
    document.getElementById('active').textContent = 'idle';
    document.getElementById('checks').innerHTML = '';
    // Perf panel is hidden on OBD via CSS but still in the DOM; clear it so
    // a Reaper→OBD→Reaper switch doesn't briefly show the prior Reaper values
    // before the next poll completes.
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

      if (r.status >= 500 || data.status === 'down') {
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

  function render(backend, d) {
    document.getElementById('updated').textContent = 'Updated ' + new Date().toLocaleTimeString();
    document.getElementById('updatedAt').textContent = d.ts ? new Date(d.ts * 1000).toLocaleString() : '--';

    const overall = document.getElementById('overall');
    if (d.status === 'up') {
      overall.innerHTML = '<span class="good">UP</span>' + (d.version ? ' <span class="small">' + d.version + '</span>' : '');
    } else {
      overall.innerHTML = '<span class="bad">DOWN</span>';
    }

    const upstream = document.getElementById('upstream');
    upstream.textContent = backend === 'obd' ? 'Orthos (Chris @ tailnet)'
                         : backend === 'lilblue' ? 'Kaydanski (RX 6600)'
                         : 'Master Blaster (RX 9070 XT)';

    const modelInfo = (d.model && d.model.id) ? d.model.id : (d.model && d.model.name) || '--';
    const modelAvail = d.model && d.model.available;
    document.getElementById('model').innerHTML = modelInfo + (modelInfo === '--' ? '' :
      ' <span class="small ' + (modelAvail ? 'good' : 'bad') + '">' + (modelAvail ? 'available' : 'missing') + '</span>');

    // Tracker panels (LilBlue/Reaper only)
    if (d.traffic) renderTracker(d);

    // Health checks (last test result if returned alongside status, otherwise blank)
    if (d.checks) renderChecks(d);
  }

  function renderTracker(d) {
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

    const current = d.current || {};
    document.getElementById('active').textContent = current.method
      ? (current.method + ' ' + current.path + ' (' + (current.model || '?') + ') started ' + Math.round((Date.now()/1000) - current.started) + 's ago')
      : 'idle';

    const rows = (t.metrics || []).map(m => {
      const sec = m.duration_ms ? (m.duration_ms / 1000).toFixed(2) + 's' : '--';
      const pillCls = m.status >= 200 && m.status < 300 ? 'status-ok'
                   : m.status === 503 || m.status === 429 ? 'status-503'
                   : 'status-error';
      return '<tr><td class="small">' + new Date(m.ts * 1000).toLocaleTimeString() + '</td>'
           + '<td>' + (m.method || '') + '</td>'
           + '<td>' + (m.path || '') + '</td>'
           + '<td><span class="status-pill ' + pillCls + '">' + m.status + '</span></td>'
           + '<td>' + sec + '</td>'
           + '<td>' + (m.model || '') + '</td>'
           + '<td class="small">' + (m.category || '') + '</td></tr>';
    }).join('');
    document.getElementById('trafficBody').innerHTML = rows;

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
  });
  </script>
</body>
</html>
""".encode("utf-8")
