INDEX_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LilBlue Dashboard</title>
  <style>
    :root { color-scheme: dark; --bg:#010608; --panel:#080d14; --panel2:#0d1520; --line:#1a2a3a; --text:#ddeeff; --muted:#6a8aaa; --good:#00d9a0; --bad:#ff3366; --warn:#ffaa00; --blue:#4db8ff; --lilblue:#1a9fff; --ash:#0b1420; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 18% -10%, rgba(26, 159, 255, .18), transparent 32%), radial-gradient(circle at 82% -4%, rgba(0, 200, 255, .12), transparent 28%), linear-gradient(180deg, #040810, #010305 48%, #000); color:var(--text); }
    header { padding:18px 22px; border-bottom:1px solid #1a3050; display:flex; align-items:center; justify-content:space-between; gap:16px; background:linear-gradient(90deg, rgba(1, 4, 10, .98), rgba(8, 18, 32, .94) 55%, rgba(2, 18, 40, .72)); box-shadow:0 10px 30px rgba(0,0,0,.60), inset 0 -1px 0 rgba(26, 159, 255, .20); }
    .brand { display:flex; align-items:center; gap:10px; min-width:0; }
    h1 { margin:0; font-size:22px; font-weight:700; color:#a8d8ff; text-shadow:0 0 6px rgba(77, 184, 255, .55), 0 0 18px rgba(26, 159, 255, .38), 0 0 36px rgba(0, 160, 255, .20); animation:lilblue-pulse 5s infinite alternate ease-in-out; }
    @keyframes lilblue-pulse {
      0%   { color:#9dd0ff; text-shadow:0 0 5px rgba(77,184,255,.45), 0 0 15px rgba(26,159,255,.30), 0 0 30px rgba(0,140,255,.16); }
      50%  { color:#c0e4ff; text-shadow:0 0 8px rgba(100,200,255,.60), 0 0 22px rgba(40,170,255,.42), 0 0 44px rgba(0,160,255,.22); }
      100% { color:#a8d8ff; text-shadow:0 0 6px rgba(77,184,255,.50), 0 0 18px rgba(26,159,255,.35), 0 0 36px rgba(0,150,255,.18); }
    }
    main { position:relative; padding:20px; display:grid; gap:16px; max-width:1320px; margin:0 auto; isolation:isolate; }
    main::before { content:""; position:absolute; inset:8px; border-radius:10px; background:radial-gradient(circle at 20% 10%, rgba(26,159,255,.07), transparent 34%), radial-gradient(circle at 80% 20%, rgba(0,200,255,.06), transparent 30%), rgba(0,0,0,.06); opacity:.75; z-index:-1; pointer-events:none; }
    .grid { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:12px; }
    .grid3 { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; }
.panel { background:linear-gradient(180deg, #0d1520, #060a10); border:1px solid var(--line); border-radius:8px; padding:14px; box-shadow:0 8px 24px rgba(0,0,0,.50), inset 0 1px 0 rgba(77,184,255,.05); }
    .status-card { min-height:118px; overflow:hidden; }
    .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
    .value { font-size:22px; margin-top:8px; line-height:1.22; overflow-wrap:anywhere; }
    .small { color:var(--muted); font-size:13px; line-height:1.45; }
    .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .blue { color:var(--blue); }
    button { border:1px solid #1a6aaa; background:linear-gradient(180deg, #061428, #020810); color:#a8d8ff; border-radius:6px; padding:10px 13px; cursor:pointer; font-weight:650; box-shadow:inset 0 1px 0 rgba(77, 184, 255, .15); }
    button:hover { background:linear-gradient(180deg, #0d2040, #04100e); border-color:#4db8ff; }
    .health-head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; flex-wrap:wrap; }
    .health-status { font-size:22px; font-weight:700; margin-top:6px; }
    .checks { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:8px; margin-top:12px; }
    .check { border:1px solid var(--line); background:#070c14; border-radius:6px; padding:9px 10px; min-height:64px; }
    .check.ok { border-color:#00d9a0; background:#041a14; }
    .check.fail { border-color:#ff3366; background:#180614; }
    .check .name { font-weight:700; }
    .check .detail { margin-top:4px; font-size:12px; color:var(--muted); overflow-wrap:anywhere; }

    /* VRAM panel */
    .vram-idle { display:flex; align-items:center; justify-content:center; min-height:120px; }
    .vram-idle-text { font-size:18px; color:var(--muted); font-weight:600; letter-spacing:.02em; }
    .vram-list { display:grid; gap:10px; margin-top:10px; }
    .vram-card { border:1px solid #1a4060; background:linear-gradient(135deg, #04101e, #060c18); border-radius:8px; padding:14px 16px; display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; }
    .vram-card.loaded { border-color:#1a9fff; background:linear-gradient(135deg, #04101e, #071828); box-shadow:0 0 18px rgba(26,159,255,.12); }
    .vram-model-name { font-size:18px; font-weight:700; color:#a8d8ff; }
    .vram-model-meta { font-size:12px; color:var(--muted); margin-top:4px; }
    .vram-badges { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .badge { border-radius:999px; padding:4px 12px; font-size:13px; font-weight:700; border:1px solid; }
    .badge-vram { background:#071828; border-color:#1a6aaa; color:#4db8ff; font-size:15px; }
    .badge-expiry { background:#0a1818; border-color:#006644; color:#00d9a0; }
    .badge-expiry.expiring { background:#1a1000; border-color:#8a5000; color:#ffaa00; }
    .badge-size { background:#060a14; border-color:#1a2a3a; color:#6a8aaa; }

table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .table-scroll { max-height:360px; overflow:auto; border:1px solid var(--line); border-radius:6px; margin-top:10px; }
    .table-scroll table { min-width:600px; }
    .table-scroll thead th { position:sticky; top:0; background:var(--panel); z-index:1; }
    .size-cell { white-space:nowrap; }
    @media (prefers-reduced-motion: reduce) { h1 { animation:none; } }
    @media (max-width: 1000px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr 1fr; } }
    @media (max-width: 600px) { .grid, .grid3, .workgrid, .checks { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>LilBlue Dashboard</h1>
    <div class="small" id="updated">Loading...</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel status-card"><div class="label">LilBlue</div><div class="value" id="status">...</div></div>
      <div class="panel status-card"><div class="label">Model</div><div class="value" id="model">...</div></div>
      <div class="panel status-card"><div class="label">Version</div><div class="value" id="version">...</div></div>
      <div class="panel status-card"><div class="label">VRAM</div><div class="value" id="vramStatus">...</div></div>
    </section>
    <section class="panel">
      <div class="health-head">
        <div>
          <div class="label">One Button Verification</div>
          <div id="healthResult" class="health-status warn">Not run yet</div>
          <div id="healthMeta" class="small">Tests reachability, model list, and a tiny generation through LilBlue.</div>
        </div>
        <button onclick="runHealthTest()">Test LilBlue</button>
      </div>
      <div id="healthChecks" class="checks"></div>
    </section>
    <section class="panel">
      <div class="label">Currently Loaded in VRAM</div>
      <div id="vramModels"></div>
    </section>
    <section class="grid3">
      <div class="panel"><div class="label">Installed Models</div><div class="value" id="statInstalled">...</div></div>
      <div class="panel"><div class="label">Total Disk Usage</div><div class="value" id="statDisk">...</div></div>
      <div class="panel"><div class="label">VRAM In Use</div><div class="value" id="statVram">...</div></div>
    </section>
    <section class="panel">
      <div class="label">Available Models</div>
      <div class="table-scroll"><table><thead><tr><th>Model</th><th>Family</th><th>Params</th><th>Quant</th><th>Size</th></tr></thead><tbody id="modelTable"></tbody></table></div>
    </section>
  </main>
  <script>
    const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function fmtBytes(b) {
      b = Number(b || 0);
      if (b >= 1e9) return (b/1e9).toFixed(1) + ' GB';
      if (b >= 1e6) return (b/1e6).toFixed(0) + ' MB';
      return b + ' B';
    }
    function fmtExpiry(ts) {
      if (!ts) return null;
      const diff = Math.round((new Date(ts) - Date.now()) / 1000);
      if (diff <= 0) return { label: 'expired', expiring: true };
      if (diff < 60) return { label: diff + 's', expiring: true };
      const mins = Math.round(diff / 60);
      return { label: mins + 'm', expiring: mins < 5 };
    }
    async function refresh() {
      try {
        const s = await (await fetch('/api/status')).json();
        renderStatus(s);
      } catch(e) {
        document.getElementById('updated').textContent = 'Refresh failed - ' + new Date().toLocaleTimeString();
        document.getElementById('status').innerHTML = '<span class="bad">Down</span>';
      }
    }
    function renderStatus(s) {
      document.getElementById('updated').textContent = 'Auto-refresh every 10s — Updated ' + new Date().toLocaleTimeString();
      const up = s.status === 'up';
      const loaded = s.loaded || [];
      document.getElementById('status').innerHTML = up ? '<span class="good">Up</span>' : '<span class="bad">Down</span>';
      document.getElementById('model').innerHTML = up
        ? `<span class="${s.model?.available ? 'good' : 'bad'}">${s.model?.available ? 'Available' : 'Unavailable'}</span><div class="small">${esc(s.model?.id || '?')}</div>`
        : '<span class="bad">—</span>';
      document.getElementById('version').innerHTML = up ? `<span class="blue">${esc(s.version || '?')}</span>` : '<span class="bad">—</span>';
      document.getElementById('vramStatus').innerHTML = loaded.length > 0
        ? `<span class="warn">Active</span><div class="small">${loaded.length} model${loaded.length !== 1 ? 's' : ''} loaded</div>`
        : `<span class="good">Idle</span>`;
      renderVram(loaded);
      renderAvailable(s.available || []);
      renderGrid3(s);
    }
    function renderVram(models) {
      const el = document.getElementById('vramModels');
      if (!models.length) {
        el.innerHTML = '<div class="vram-idle"><span class="vram-idle-text">Idle — no models in VRAM</span></div>';
        return;
      }
      el.innerHTML = '<div class="vram-list">' + models.map(m => {
        const name = m.name || m.model || '?';
        const vram = m.size_vram ? fmtBytes(m.size_vram) : null;
        const size = m.size ? fmtBytes(m.size) : null;
        const expiry = m.expires_at ? fmtExpiry(m.expires_at) : null;
        const vramBadge = vram ? `<span class="badge badge-vram">${esc(vram)} VRAM</span>` : '';
        const expiryBadge = expiry ? `<span class="badge badge-expiry${expiry.expiring ? ' expiring' : ''}">expires ${esc(expiry.label)}</span>` : '';
        const sizeBadge = size ? `<span class="badge badge-size">${esc(size)} total</span>` : '';
        return `<div class="vram-card loaded">
          <div>
            <div class="vram-model-name">${esc(name)}</div>
            <div class="vram-model-meta">Loaded and ready</div>
          </div>
          <div class="vram-badges">${vramBadge}${expiryBadge}${sizeBadge}</div>
        </div>`;
      }).join('') + '</div>';
    }
    function renderAvailable(models) {
      document.getElementById('modelTable').innerHTML = models.map(m => {
        const d = m.details || {};
        return `<tr>
          <td><strong>${esc(m.name || m.model || '?')}</strong></td>
          <td>${esc(d.family || '—')}</td>
          <td>${esc(d.parameter_size || '—')}</td>
          <td>${esc(d.quantization_level || '—')}</td>
          <td class="size-cell">${fmtBytes(m.size)}</td>
        </tr>`;
      }).join('');
    }
    function renderGrid3(s) {
      const avail = s.available || [];
      const loaded = s.loaded || [];
      const totalSize = avail.reduce((a, m) => a + (m.size || 0), 0);
      const loadedVram = loaded.reduce((a, m) => a + (m.size_vram || 0), 0);
      document.getElementById('statInstalled').innerHTML =
        `<span class="blue">${avail.length}</span>`;
      document.getElementById('statDisk').innerHTML =
        `<span class="blue">${fmtBytes(totalSize)}</span>`;
      document.getElementById('statVram').innerHTML = loadedVram > 0
        ? `<span class="warn">${fmtBytes(loadedVram)}</span>`
        : `<span class="good">None</span>`;
    }
    async function runHealthTest() {
      const result = document.getElementById('healthResult');
      const meta = document.getElementById('healthMeta');
      result.className = 'health-status warn';
      result.textContent = 'Testing...';
      meta.textContent = 'Running LilBlue health check now.';
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
      result.textContent = data.ok ? 'LilBlue test passed' : `${data.failed || 0} check(s) failed`;
      meta.textContent = `Completed in ${data.duration_ms || 0}ms at ${new Date((data.ts || Date.now()/1000)*1000).toLocaleTimeString()}`;
      document.getElementById('healthChecks').innerHTML = (data.checks || []).map(c =>
        `<div class="check ${c.ok ? 'ok' : 'fail'}"><div class="name ${c.ok ? 'good' : 'bad'}">${c.ok ? 'OK' : 'FAIL'} — ${esc(c.name)}</div><div class="detail">${esc(c.detail || '')}</div></div>`
      ).join('');
    }
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>""".encode("utf-8")
