"""AI Fleet Dashboard outer-shell HTML.

Thin tab strip + iframe area. The four tabs each load a real page in an
iframe carrying the user's BirdMug-Auth cookie:

  REAPER / LILBLUE / OBD   -> the per-service base dashboards at their
                              real public URLs (full original chrome,
                              their own headers, colors, branding)
  MODELS                   -> /models on this same origin (fleet-level
                              model management page served by app.py)

Previous iteration loaded the three base dashboards with `?embed=1` and
overlayed a generic "AI Fleet" header on top. Kyle's directive 2026-05-21
was that this squashed the per-service identity — each tab should look
exactly like its original page. So the outer header is gone and the
`?embed=1` param is dropped. The inner dashboards' embed-mode CSS rule
(`html.embed > body > header { display:none; }`) is now dead code since
the param is never sent — left in place harmlessly in case the param is
ever appended for manual testing or external embedding.
"""

INDEX_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Fleet</title>
  <link rel="icon" href="/fleet.png" sizes="any">
  <link rel="shortcut icon" href="/fleet.png">
  <style>
    :root { color-scheme: dark; --bg:#000; --line:#1a1a1a; --bone:#ecdfe1; --muted:#7a7a7a; }
    * { box-sizing:border-box; }
    html, body { margin:0; padding:0; height:100%; background:#000; color:var(--bone); font-family:Segoe UI, system-ui, sans-serif; }
    body { display:flex; flex-direction:column; }
    nav.tabs { display:flex; gap:0; padding:0 16px; background:#000; border-bottom:1px solid var(--line); flex:0 0 auto; height:38px; align-items:stretch; }
    nav.tabs button { background:transparent; border:none; border-bottom:2px solid transparent; color:var(--muted); padding:0 16px; font-size:12px; font-weight:700; letter-spacing:.10em; text-transform:uppercase; cursor:pointer; transition:color .15s, border-color .15s, text-shadow .15s; }
    nav.tabs button:hover { color:var(--bone); }
    /* Per-tab color legend — matches each backend's own brand color so
       the tab strip reads as a color key. */
    nav.tabs button[data-backend="reaper"]  { --tab-color:#d3133b; }
    nav.tabs button[data-backend="lilblue"] { --tab-color:#1a9fff; }
    nav.tabs button[data-backend="obd"]     { --tab-color:#ff3b14; }
    nav.tabs button[data-backend="models"]  { --tab-color:#a0a0a0; }
    nav.tabs button.active { color:var(--tab-color); border-bottom-color:var(--tab-color); text-shadow:0 0 8px color-mix(in srgb, var(--tab-color) 55%, transparent); }
    nav.tabs .target-url { margin-left:auto; align-self:center; color:var(--muted); font-size:12px; font-family:Consolas, monospace; }
    nav.tabs .target-url a { color:var(--muted); text-decoration:none; }
    nav.tabs .target-url a:hover { color:var(--bone); text-decoration:underline; }
    main { flex:1 1 auto; position:relative; display:flex; min-height:0; background:#000; }
    iframe.dashboard-frame { flex:1 1 auto; width:100%; height:100%; border:0; background:#000; }
    /* Loading shim shown until the iframe fires its load event. Avoids a
       brief flash of blank-black when switching tabs. */
    .loading { position:absolute; inset:0; display:none; align-items:center; justify-content:center; pointer-events:none; color:var(--muted); font-size:13px; letter-spacing:.04em; text-transform:uppercase; background:rgba(0,0,0,.18); }
    .loading.show { display:flex; }
    @media (max-width: 1000px) {
      nav.tabs { padding:0 8px; overflow-x:auto; }
      nav.tabs button { padding:0 10px; }
      nav.tabs .target-url { display:none; }
    }
  </style>
</head>
<body>
  <nav class="tabs" id="tabs">
    <button data-backend="reaper" class="active">REAPER</button>
    <button data-backend="lilblue">LILBLUE</button>
    <button data-backend="obd">OBD</button>
    <button data-backend="models">MODELS</button>
    <span class="target-url"><a id="openInNew" href="#" target="_blank" rel="noopener">open in new tab ↗</a></span>
  </nav>
  <main>
    <iframe id="frame" class="dashboard-frame" name="dashboard" title="Dashboard" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals"></iframe>
    <div class="loading" id="loading">Loading…</div>
  </main>
  <script>
  const BACKENDS = ['reaper','lilblue','obd','models'];
  // Each tab loads the canonical original page — NO ?embed=1 — so it
  // renders with its full native chrome (header, branding, colors).
  const BACKEND_URL = {
    reaper:  'https://reaper.birdmug.com/',
    lilblue: 'https://lilblue.birdmug.com/',
    obd:     'https://obd.birdmug.com/',
    models:  '/models',
  };
  const BACKEND_PUBLIC_URL = {
    reaper:  'https://reaper.birdmug.com/',
    lilblue: 'https://lilblue.birdmug.com/',
    obd:     'https://obd.birdmug.com/',
    models:  '/models',
  };

  function resolveInitialBackend() {
    const fromHash = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (BACKENDS.includes(fromHash)) return fromHash;
    if (fromHash) console.warn('AI Fleet: unknown hash backend ' + JSON.stringify(fromHash) + '; falling back.');
    const stored = (localStorage.getItem('aiFleetBackend') || '').toLowerCase();
    if (BACKENDS.includes(stored)) return stored;
    return 'reaper';
  }

  let currentBackend = resolveInitialBackend();
  let loadingTimer = null;

  function setActiveTab(name) {
    if (!BACKENDS.includes(name)) name = 'reaper';
    currentBackend = name;
    localStorage.setItem('aiFleetBackend', name);
    history.replaceState(null, '', '#' + name);
    document.querySelectorAll('#tabs button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.backend === name);
    });
    document.getElementById('openInNew').href = BACKEND_PUBLIC_URL[name];

    const frame = document.getElementById('frame');
    const target = BACKEND_URL[name];
    if (frame.src !== new URL(target, location.origin).href) {
      showLoading();
      frame.src = target;
    }
  }

  function showLoading() {
    document.getElementById('loading').classList.add('show');
    clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
      document.getElementById('loading').classList.remove('show');
    }, 8000);
  }
  function hideLoading() {
    document.getElementById('loading').classList.remove('show');
    clearTimeout(loadingTimer);
  }

  document.querySelectorAll('#tabs button').forEach(btn => {
    btn.addEventListener('click', () => setActiveTab(btn.dataset.backend));
  });

  document.getElementById('frame').addEventListener('load', hideLoading);

  window.addEventListener('hashchange', () => {
    const h = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (BACKENDS.includes(h) && h !== currentBackend) setActiveTab(h);
    else if (h && !BACKENDS.includes(h)) console.warn('AI Fleet: unknown hash backend ' + JSON.stringify(h) + '; ignoring.');
  });

  setActiveTab(currentBackend);
  </script>
</body>
</html>
""".encode("utf-8")
