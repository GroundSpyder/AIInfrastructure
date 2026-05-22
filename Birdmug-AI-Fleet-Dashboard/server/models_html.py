"""Models management page — served at /models, embedded as the MODELS tab.

This is the GUI Kyle asked for 2026-05-21: see loaded models per host,
add/load/unload/delete models, choose GPU-strict vs CPU-spillover, set
keep-alive, manage the warm-set, and tune NSSM env vars
(OLLAMA_MAX_LOADED_MODELS / OLLAMA_KEEP_ALIVE).

Single-file HTML+CSS+JS. Talks to /api/models/* via fetch.
"""

MODELS_HTML: bytes = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fleet Models</title>
  <link rel="icon" href="/fleet.png">
  <style>
    :root { color-scheme: dark;
      --bg:#050608; --panel:#0c0f14; --panel2:#11161e; --line:#1d2531;
      --text:#d8e0ec; --muted:#74819a; --bone:#ecf0f7;
      --good:#22d39c; --bad:#ff4561; --warn:#ffba2b; --accent:#7ec5ff;
      --mb:#ff8b32;        /* MB orange — RX 9070 XT */
      --kayd:#3aa6ff;      /* Kaydanski blue — RX 6600 */
    }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Segoe UI, system-ui, sans-serif; background:radial-gradient(circle at 12% -8%, rgba(126,197,255,.08), transparent 35%), linear-gradient(180deg, #060810, #020306 60%, #000); color:var(--text); min-height:100vh; }
    .wrap { padding:18px 22px 36px; max-width:1480px; margin:0 auto; }
    .topbar { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:18px; }
    h1 { margin:0; font-size:18px; font-weight:700; letter-spacing:.05em; color:var(--bone); }
    .small { color:var(--muted); font-size:12px; }
    .grid-hosts { display:grid; grid-template-columns:repeat(auto-fit, minmax(560px, 1fr)); gap:18px; align-items:start; }
    .hostcard { background:linear-gradient(180deg, var(--panel), var(--panel2) 70%, var(--panel)); border:1px solid var(--line); border-radius:10px; padding:16px; box-shadow:0 8px 24px rgba(0,0,0,.50); }
    .hostcard[data-host="mb"]        { border-top:2px solid var(--mb); }
    .hostcard[data-host="kaydanski"] { border-top:2px solid var(--kayd); }
    .hosthead { display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .hosthead .name { font-size:16px; font-weight:700; letter-spacing:.04em; }
    .hosthead .meta { color:var(--muted); font-size:12px; font-family:Consolas, monospace; }
    .vrambar { height:10px; border-radius:999px; background:#020306; border:1px solid var(--line); overflow:hidden; margin:6px 0 14px; }
    .vrambar > div { height:100%; background:linear-gradient(90deg, #22d39c, #7ec5ff, #ff8b32); width:0%; transition:width .4s ease; }
    section.block { margin-top:14px; }
    section.block h3 { margin:0 0 8px; font-size:11px; letter-spacing:.10em; text-transform:uppercase; color:var(--muted); font-weight:700; }
    .model-row { display:grid; grid-template-columns: 1fr auto auto; gap:8px; align-items:center; padding:8px 10px; background:#070a10; border:1px solid var(--line); border-radius:7px; margin-bottom:6px; }
    .model-row .name { font-family:Consolas, monospace; font-size:13px; color:var(--bone); overflow-wrap:anywhere; }
    .model-row .meta { color:var(--muted); font-size:11px; font-family:Consolas, monospace; white-space:nowrap; }
    .model-row .actions { display:flex; gap:6px; }
    .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; letter-spacing:.04em; border:1px solid var(--line); background:#0a0d13; color:var(--muted); margin-left:6px; }
    .pill.gpu  { color:var(--good); border-color:#1a6b54; background:#04241b; }
    .pill.cpu  { color:var(--warn); border-color:#6b5a1a; background:#231d04; }
    button { font: inherit; border:1px solid var(--line); background:linear-gradient(180deg, #0e131c, #050810); color:var(--bone); border-radius:6px; padding:6px 11px; font-size:12px; font-weight:600; cursor:pointer; transition:border-color .15s, background .15s, color .15s; }
    button:hover { border-color:#3a4a66; }
    button.primary { border-color:#1a4a78; color:#bfe0ff; }
    button.primary:hover { border-color:#3a8fd0; background:linear-gradient(180deg, #0a1828, #050810); }
    button.danger { border-color:#6a1a2a; color:#ffb0b8; }
    button.danger:hover { border-color:#c83048; background:linear-gradient(180deg, #1a0608, #050203); }
    button:disabled { opacity:.4; cursor:not-allowed; }
    .controls { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; align-items:center; }
    .controls label { font-size:12px; color:var(--muted); display:flex; align-items:center; gap:6px; }
    .controls input[type=text], .controls select { background:#070a10; border:1px solid var(--line); color:var(--bone); border-radius:5px; padding:5px 8px; font:inherit; font-size:12px; }
    .controls input[type=checkbox] { accent-color:var(--good); }
    .add-row { display:flex; gap:8px; align-items:center; margin-top:6px; }
    .add-row input { flex:1; min-width:160px; }
    .empty { color:var(--muted); font-size:12px; padding:8px; font-style:italic; }
    .err { color:var(--bad); font-size:12px; padding:6px 8px; border:1px solid #4a1622; background:#1a0608; border-radius:6px; margin-bottom:6px; }
    .ok { color:var(--good); font-size:12px; padding:6px 8px; border:1px solid #1a6b54; background:#04241b; border-radius:6px; margin-bottom:6px; }
    .envgrid { display:grid; grid-template-columns:1fr 1.4fr auto; gap:6px; align-items:center; }
    .envgrid input { background:#070a10; border:1px solid var(--line); color:var(--bone); border-radius:5px; padding:4px 7px; font:inherit; font-family:Consolas, monospace; font-size:12px; }
    .modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.72); display:none; align-items:center; justify-content:center; z-index:100; }
    .modal-backdrop.show { display:flex; }
    .modal { background:#0c1018; border:1px solid var(--line); border-radius:10px; padding:20px; min-width:380px; max-width:520px; box-shadow:0 20px 60px rgba(0,0,0,.80); }
    .modal h2 { margin:0 0 8px; font-size:14px; color:var(--bad); letter-spacing:.04em; }
    .modal p { color:var(--text); font-size:13px; line-height:1.5; margin:0 0 12px; }
    .modal code { font-family:Consolas, monospace; color:var(--accent); }
    .modal input { width:100%; background:#070a10; border:1px solid var(--line); color:var(--bone); border-radius:5px; padding:8px 10px; font:inherit; margin-bottom:12px; }
    .modal-actions { display:flex; gap:8px; justify-content:flex-end; }
    .toasts { position:fixed; bottom:18px; right:18px; display:flex; flex-direction:column-reverse; gap:8px; z-index:200; }
    .toast { padding:10px 14px; border-radius:6px; font-size:13px; max-width:480px; border:1px solid var(--line); background:#0c1018; box-shadow:0 8px 24px rgba(0,0,0,.60); }
    .toast.ok  { border-color:#1a6b54; color:#caffeb; background:linear-gradient(180deg, #041a14, #02100c); }
    .toast.err { border-color:#6a1a2a; color:#ffd5c8; background:linear-gradient(180deg, #1a0608, #100203); }
    .pull-progress { font-family:Consolas, monospace; font-size:11px; color:var(--muted); margin-top:6px; max-height:140px; overflow:auto; padding:6px 8px; background:#040608; border:1px solid var(--line); border-radius:6px; }
    .pull-bar { height:8px; border-radius:999px; background:#020306; border:1px solid var(--line); overflow:hidden; margin-top:4px; }
    .pull-bar > div { height:100%; background:linear-gradient(90deg, var(--accent), var(--good)); width:0%; transition:width .3s ease; }
    .warmlist { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
    .warmtag { background:#070a10; border:1px solid var(--line); border-radius:999px; padding:3px 9px 3px 11px; font-family:Consolas, monospace; font-size:12px; display:inline-flex; align-items:center; gap:6px; }
    .warmtag button { padding:0 5px; font-size:11px; border:none; background:transparent; color:var(--muted); }
    .warmtag button:hover { color:var(--bad); }
  </style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <h1>FLEET MODELS</h1>
    <div class="small" id="updated">…</div>
  </div>

  <div class="grid-hosts" id="hosts"></div>
</div>

<div class="modal-backdrop" id="modal">
  <div class="modal">
    <h2>Confirm delete</h2>
    <p>This will permanently remove <code id="modalModel"></code> from <code id="modalHost"></code>. Type the model name to confirm:</p>
    <input id="modalInput" autocomplete="off" spellcheck="false" placeholder="model name">
    <div class="modal-actions">
      <button id="modalCancel">Cancel</button>
      <button id="modalConfirm" class="danger" disabled>Delete</button>
    </div>
  </div>
</div>

<div class="toasts" id="toasts"></div>

<script>
'use strict';

const KEEP_ALIVE_CHOICES = ['0s', '5m', '1h', '24h', '-1'];
const HOST_ORDER = ['mb', 'kaydanski'];

let hosts = [];
let state = {};  // alias -> { ps, tags, env, warmSet }

function fmtBytes(n) {
  if (!n) return '0';
  const u = ['B','KB','MB','GB','TB'];
  let i = 0; let v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(v >= 100 ? 0 : 1) + ' ' + u[i];
}

// Build a DOM element via textContent for any caller-supplied string,
// avoiding the XSS surface that innerHTML opens up. Use this whenever
// rendering a model name, host alias, or error string from upstream.
function el(tag, opts) {
  const e = document.createElement(tag);
  if (!opts) return e;
  if (opts.className) e.className = opts.className;
  if (opts.text != null) e.textContent = String(opts.text);
  if (opts.title) e.title = String(opts.title);
  if (opts.dataset) for (const k in opts.dataset) e.dataset[k] = opts.dataset[k];
  if (opts.style) for (const k in opts.style) e.style[k] = opts.style[k];
  if (opts.attrs) for (const k in opts.attrs) e.setAttribute(k, opts.attrs[k]);
  if (opts.children) for (const c of opts.children) if (c) e.appendChild(c);
  return e;
}

function toast(msg, kind) {
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || 'ok');
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 7000);
}

async function api(method, path, body) {
  const opts = { method, headers: {'Content-Type': 'application/json'} };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  // Read the body as text exactly once — calling .json() then .text()
  // throws "body already read." Then try to parse the text as JSON.
  const text = await r.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch (e) { data = { error: 'bad_json', detail: text.slice(0, 500) }; }
  if (!r.ok) {
    const msg = data.detail || data.error || ('HTTP ' + r.status);
    throw new Error(msg);
  }
  return data;
}

async function loadAll() {
  try {
    const h = await api('GET', '/api/models/hosts');
    hosts = h.hosts;
  } catch (e) {
    toast('failed to list hosts: ' + e.message, 'err');
    return;
  }
  // Sort by HOST_ORDER for deterministic display
  hosts.sort((a, b) => HOST_ORDER.indexOf(a.alias) - HOST_ORDER.indexOf(b.alias));
  await Promise.all(hosts.map(h => refreshHost(h.alias)));
  document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
  render();
}

async function refreshHost(alias) {
  state[alias] = state[alias] || {};
  // .catch on each so a single backend failure doesn't sink the other.
  // Promise.all without these catches would reject the whole batch on
  // first error, and the outer try/catch wouldn't add value (no chance
  // to throw with both catches absorbing). So no outer try/catch here.
  const [ps, tags] = await Promise.all([
    api('GET', '/api/models/' + alias + '/ps').catch(e => ({ error: e.message })),
    api('GET', '/api/models/' + alias + '/tags').catch(e => ({ error: e.message })),
  ]);
  state[alias].ps = ps;
  state[alias].tags = tags;
  // Env + warm-set are slower (SSH). Fire and forget; render again on arrival.
  api('GET', '/api/models/' + alias + '/env').then(r => { state[alias].env = r.env; render(); })
    .catch(e => { state[alias].envErr = e.message; render(); });
  api('GET', '/api/models/' + alias + '/warm-set').then(r => { state[alias].warmSet = r.warm_set; render(); })
    .catch(e => { state[alias].warmErr = e.message; render(); });
}

function render() {
  const container = document.getElementById('hosts');
  container.innerHTML = '';
  hosts.forEach(h => container.appendChild(renderHost(h)));
}

function renderHost(host) {
  const card = document.createElement('div');
  card.className = 'hostcard';
  card.dataset.host = host.alias;
  const st = state[host.alias] || {};

  const head = el('div', {
    className: 'hosthead',
    children: [
      el('div', {
        children: [
          el('div', { className: 'name', text: host.label }),
          el('div', { className: 'meta', text: host.gpu + ' · ' + host.backend }),
        ],
      }),
    ],
  });
  card.appendChild(head);

  // VRAM summary
  const ps = st.ps && !st.ps.error ? st.ps : { models: [] };
  const loaded = ps.models || [];
  const totalVram = loaded.reduce((a, m) => a + (m.size_vram || 0), 0);
  const totalSize = loaded.reduce((a, m) => a + (m.size || 0), 0);
  const cpuOverflow = Math.max(0, totalSize - totalVram);
  const vramTitle = document.createElement('div');
  vramTitle.className = 'small';
  vramTitle.textContent = 'Resident: ' + fmtBytes(totalVram) + ' VRAM' + (cpuOverflow ? ' + ' + fmtBytes(cpuOverflow) + ' RAM' : '');
  card.appendChild(vramTitle);
  const bar = document.createElement('div');
  bar.className = 'vrambar';
  const pct = totalSize > 0 ? Math.min(100, (totalVram / totalSize) * 100) : 0;
  bar.innerHTML = '<div style="width:' + pct.toFixed(1) + '%"></div>';
  card.appendChild(bar);

  if (st.ps && st.ps.error) {
    const e = document.createElement('div');
    e.className = 'err';
    e.textContent = 'ollama unreachable: ' + (st.ps.detail || st.ps.error);
    card.appendChild(e);
  }

  // Loaded section
  const loadedBlock = el('section', {
    className: 'block',
    children: [el('h3', { text: 'Loaded (' + loaded.length + ')' })],
  });
  if (loaded.length === 0) {
    loadedBlock.appendChild(el('div', { className: 'empty', text: 'no models resident' }));
  } else {
    loaded.forEach(m => loadedBlock.appendChild(renderLoadedRow(host.alias, m)));
  }
  card.appendChild(loadedBlock);

  // Installed (not loaded) section
  const tags = (st.tags && !st.tags.error ? st.tags.models : []) || [];
  const loadedNames = new Set(loaded.map(m => m.name));
  const installed = tags.filter(t => !loadedNames.has(t.name));
  const installedBlock = el('section', {
    className: 'block',
    children: [el('h3', { text: 'Installed (' + installed.length + ')' })],
  });
  if (installed.length === 0) {
    installedBlock.appendChild(el('div', { className: 'empty', text: 'no other models installed' }));
  } else {
    installed.forEach(m => installedBlock.appendChild(renderInstalledRow(host.alias, m)));
  }
  card.appendChild(installedBlock);

  // Pull-new
  const pullBlock = el('section', {
    className: 'block',
    children: [el('h3', { text: 'Pull New' })],
  });
  const pullInput = el('input', {
    attrs: { type: 'text', placeholder: 'e.g. qwen2.5:14b, bge-m3:latest', autocomplete: 'off' },
  });
  const pullBtn = el('button', { className: 'primary', text: 'Pull' });
  pullBtn.addEventListener('click', () => doPull(host.alias, pullInput.value.trim(), pullBlock));
  pullBlock.appendChild(el('div', { className: 'add-row', children: [pullInput, pullBtn] }));
  card.appendChild(pullBlock);

  // Warm-set editor
  const wsBlock = el('section', {
    className: 'block',
    children: [el('h3', { text: 'Auto-warm set (used by AI-Resume on boot)' })],
  });
  const ws = st.warmSet || { chat: [], embed: [] };
  ['chat', 'embed'].forEach(group => {
    const row = el('div', {
      className: 'controls',
      children: [el('label', { style: { minWidth: '55px' }, text: group + ':' })],
    });
    const list = el('div', { className: 'warmlist' });
    (ws[group] || []).forEach(m => {
      const removeBtn = el('button', { attrs: { title: 'remove' }, text: '×' });
      removeBtn.addEventListener('click', () => {
        ws[group] = ws[group].filter(x => x !== m);
        saveWarmSet(host.alias, ws);
      });
      const tag = el('span', {
        className: 'warmtag',
        children: [document.createTextNode(m + ' '), removeBtn],
      });
      list.appendChild(tag);
    });
    const input = el('input', {
      attrs: { type: 'text', placeholder: '+ add ' + group },
      style: { width: '180px' },
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const m = input.value.trim();
        if (m) {
          ws[group] = [...(ws[group] || []), m];
          saveWarmSet(host.alias, ws);
        }
        input.value = '';
      }
    });
    list.appendChild(input);
    row.appendChild(list);
    wsBlock.appendChild(row);
  });
  if (st.warmErr) {
    wsBlock.appendChild(el('div', { className: 'err', text: 'warm-set ssh failed: ' + st.warmErr }));
  }
  card.appendChild(wsBlock);

  // Env / service controls
  const envBlock = el('section', {
    className: 'block',
    children: [el('h3', { text: 'NSSM env (OllamaService)' })],
  });
  const envRow = el('div', { className: 'envgrid' });
  const env = st.env || {};
  const knownKeys = ['OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_KEEP_ALIVE', 'OLLAMA_NUM_PARALLEL'];
  const keys = Array.from(new Set([...knownKeys, ...Object.keys(env)]));
  keys.forEach(k => {
    const kEl = el('input', { attrs: { disabled: 'disabled' } });
    kEl.value = k;
    const vEl = el('input', { dataset: { host: host.alias, key: k } });
    vEl.value = env[k] || '';
    const saveBtn = el('button', { text: 'Save' });
    saveBtn.addEventListener('click', () => saveEnvKey(host.alias, k, vEl.value));
    envRow.appendChild(kEl);
    envRow.appendChild(vEl);
    envRow.appendChild(saveBtn);
  });
  envBlock.appendChild(envRow);
  if (st.envErr) {
    envBlock.appendChild(el('div', { className: 'err', text: 'env ssh failed: ' + st.envErr }));
  }
  const restartBtn = el('button', { className: 'danger', text: 'Restart OllamaService' });
  restartBtn.addEventListener('click', () => doRestart(host.alias));
  envBlock.appendChild(el('div', {
    className: 'controls',
    style: { marginTop: '8px' },
    children: [restartBtn],
  }));
  card.appendChild(envBlock);

  return card;
}

function renderLoadedRow(host, m) {
  const row = el('div', { className: 'model-row' });
  // size_vram == size means fully GPU-resident; anything less and some
  // layers are on CPU. No magic threshold — Ollama reports the value
  // exactly so use it exactly.
  const vram = m.size_vram || 0;
  const onGpu = vram > 0 && vram >= m.size;
  const split = vram > 0 && !onGpu;
  const pillText = onGpu ? 'GPU' : split ? 'CPU split' : 'CPU only';
  const pillClass = onGpu ? 'pill gpu' : 'pill cpu';
  const nameCell = el('div', {
    children: [
      el('span', { className: 'name', text: m.name }),
      el('span', { className: pillClass, text: pillText }),
    ],
  });
  const metaCell = el('div', { className: 'meta' });
  metaCell.appendChild(document.createTextNode(fmtBytes(m.size)));
  if (m.expires_at) {
    metaCell.appendChild(document.createElement('br'));
    metaCell.appendChild(document.createTextNode('until ' + new Date(m.expires_at).toLocaleString()));
  }
  const actions = el('div', { className: 'actions' });
  const unloadBtn = el('button', { text: 'Unload' });
  unloadBtn.addEventListener('click', () => doUnload(host, m.name));
  actions.appendChild(unloadBtn);
  row.appendChild(nameCell);
  row.appendChild(metaCell);
  row.appendChild(actions);
  return row;
}

function renderInstalledRow(host, m) {
  const row = el('div', { className: 'model-row' });
  const nameCell = el('div', {
    children: [el('span', { className: 'name', text: m.name })],
  });
  const metaCell = el('div', { className: 'meta', text: fmtBytes(m.size) });
  const actions = el('div', { className: 'actions' });
  const loadBtn = el('button', { className: 'primary', text: 'Load' });
  loadBtn.addEventListener('click', () => promptLoad(host, m.name));
  const delBtn = el('button', { className: 'danger', text: 'Delete' });
  delBtn.addEventListener('click', () => promptDelete(host, m.name));
  actions.appendChild(loadBtn);
  actions.appendChild(delBtn);
  row.appendChild(nameCell);
  row.appendChild(metaCell);
  row.appendChild(actions);
  return row;
}

function promptLoad(host, model) {
  // Quick inline prompt for keep_alive + strict_gpu
  const ka = prompt('keep_alive for ' + model + '? (0s | 5m | 1h | 24h | -1 for forever)', '24h');
  if (ka === null) return;
  const strict = confirm('Strict GPU? OK = GPU-only (fail if too big). Cancel = allow CPU spillover.');
  doLoad(host, model, { keep_alive: ka, strict_gpu: strict });
}

async function doLoad(host, model, opts) {
  try {
    await api('POST', '/api/models/' + host + '/load', { model, ...opts });
    toast(host + ': loaded ' + model);
  } catch (e) {
    toast(host + ' load failed: ' + e.message, 'err');
  }
  refreshHost(host).then(render);
}

async function doUnload(host, model) {
  try {
    await api('POST', '/api/models/' + host + '/unload', { model });
    toast(host + ': unloaded ' + model);
  } catch (e) {
    toast(host + ' unload failed: ' + e.message, 'err');
  }
  refreshHost(host).then(render);
}

function promptDelete(host, model) {
  const modal = document.getElementById('modal');
  document.getElementById('modalModel').textContent = model;
  document.getElementById('modalHost').textContent = host;
  const input = document.getElementById('modalInput');
  const confirmBtn = document.getElementById('modalConfirm');
  input.value = '';
  confirmBtn.disabled = true;
  input.oninput = () => { confirmBtn.disabled = input.value !== model; };
  confirmBtn.onclick = async () => {
    try {
      await api('DELETE', '/api/models/' + host + '/delete', { model, confirm_name: input.value });
      toast(host + ': deleted ' + model);
      hideModal();
      refreshHost(host).then(render);
    } catch (e) {
      toast(host + ' delete failed: ' + e.message, 'err');
    }
  };
  document.getElementById('modalCancel').onclick = hideModal;
  modal.classList.add('show');
  input.focus();
}

function hideModal() {
  document.getElementById('modal').classList.remove('show');
}

async function doPull(host, model, container) {
  if (!model) { toast('enter a model name first', 'err'); return; }
  // Render progress strip inside this block
  const wrap = document.createElement('div');
  wrap.innerHTML = '<div class="pull-bar"><div></div></div><div class="pull-progress">queued…</div>';
  container.appendChild(wrap);
  const bar = wrap.querySelector('.pull-bar > div');
  const log = wrap.querySelector('.pull-progress');
  try {
    const resp = await fetch('/api/models/' + host + '/pull', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ model }),
    });
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error('HTTP ' + resp.status + ': ' + body.slice(0, 200));
    }
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    // SSE frames end with a blank line. Per spec the separator is one
    // of \\n\\n, \\r\\n\\r\\n, or \\r\\r. Use a regex that accepts any
    // of them so a proxy that normalizes line endings doesn't break
    // the parser silently.
    const FRAME_SEP = /\\r\\n\\r\\n|\\n\\n|\\r\\r/;
    const LINE_SEP  = /\\r\\n|\\n|\\r/;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(FRAME_SEP);
      buf = parts.pop();
      for (const frame of parts) {
        const lines = frame.split(LINE_SEP);
        let event = 'message', data = '';
        for (const ln of lines) {
          if (ln.startsWith('event:')) event = ln.slice(6).trim();
          else if (ln.startsWith('data:')) data += ln.slice(5).trim();
        }
        if (!data) continue;
        try {
          const evt = JSON.parse(data);
          if (event === 'error') {
            const msg = 'ERROR: ' + (evt.detail || evt.raw || JSON.stringify(evt));
            log.textContent = msg;
            log.style.color = 'var(--bad)';
            toast(host + ' pull error: ' + msg, 'err');
            return;
          }
          if (event === 'done') {
            log.textContent = 'done: ' + (evt.status || 'success');
            log.style.color = 'var(--good)';
            bar.style.width = '100%';
            setTimeout(() => refreshHost(host).then(render), 600);
            return;
          }
          const total = evt.total || 0;
          const completed = evt.completed || 0;
          if (total > 0) bar.style.width = ((completed / total) * 100).toFixed(1) + '%';
          log.textContent = (evt.status || '') + (total ? ' ' + fmtBytes(completed) + ' / ' + fmtBytes(total) : '');
        } catch (e) {
          // Persistent parse errors mean upstream stream is malformed —
          // surface as a toast in addition to the in-card log so the
          // user notices without staring at the pull box.
          const msg = 'sse parse error: ' + data.slice(0, 200);
          log.textContent = msg;
          toast(host + ' ' + msg, 'err');
        }
      }
    }
  } catch (e) {
    log.textContent = 'pull failed: ' + e.message;
    log.style.color = 'var(--bad)';
    toast(host + ' pull failed: ' + e.message, 'err');
  }
}

async function saveWarmSet(host, ws) {
  try {
    await api('PUT', '/api/models/' + host + '/warm-set', { warm_set: ws });
    state[host].warmSet = ws;
    toast(host + ': warm-set saved');
  } catch (e) {
    toast(host + ' warm-set save failed: ' + e.message, 'err');
  }
  render();
}

async function saveEnvKey(host, key, value) {
  const env = { ...(state[host].env || {}) };
  if (value === '') delete env[key];
  else env[key] = value;
  try {
    const r = await api('PUT', '/api/models/' + host + '/env', { env });
    state[host].env = r.env;
    toast(host + ': env ' + key + ' saved (restart required)');
  } catch (e) {
    toast(host + ' env save failed: ' + e.message, 'err');
  }
  render();
}

async function doRestart(host) {
  if (!confirm('Restart OllamaService on ' + host + '? Loaded models will be evicted.')) return;
  try {
    await api('POST', '/api/models/' + host + '/restart-ollama');
    toast(host + ': OllamaService restarted');
  } catch (e) {
    toast(host + ' restart failed: ' + e.message, 'err');
  }
  setTimeout(() => refreshHost(host).then(render), 3000);
}

// Initial load + 10s refresh of ps + tags (skipping env + warm-set which are SSH-bound)
loadAll();
let refreshErrorStreak = 0;
setInterval(async () => {
  for (const h of hosts) {
    try {
      const [ps, tags] = await Promise.all([
        api('GET', '/api/models/' + h.alias + '/ps').catch(e => ({ error: e.message })),
        api('GET', '/api/models/' + h.alias + '/tags').catch(e => ({ error: e.message })),
      ]);
      state[h.alias] = state[h.alias] || {};
      state[h.alias].ps = ps;
      state[h.alias].tags = tags;
    } catch (e) {
      // Promise.all itself rejected (auth expiry redirect, network drop)
      // — surface so the user isn't staring at frozen data. Throttle to
      // first occurrence + every 6th (~once per minute) to avoid spam.
      refreshErrorStreak++;
      if (refreshErrorStreak === 1 || refreshErrorStreak % 6 === 0) {
        toast('refresh failed for ' + h.alias + ': ' + (e.message || e), 'err');
      }
    }
  }
  if (refreshErrorStreak === 0) {
    document.getElementById('updated').textContent = 'updated ' + new Date().toLocaleTimeString();
  } else {
    document.getElementById('updated').textContent = 'refresh failing (' + refreshErrorStreak + ')';
  }
  // Successful poll for at least one host clears the streak so we
  // resume the normal "updated …" indicator on recovery.
  if (Object.values(state).some(s => s.ps && !s.ps.error)) refreshErrorStreak = 0;
  render();
}, 10000);
</script>
</body>
</html>
""".encode("utf-8")
