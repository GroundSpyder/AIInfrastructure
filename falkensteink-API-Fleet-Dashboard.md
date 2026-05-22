# AI Fleet Dashboard API

The AI Fleet Dashboard is the unified, **authenticated** consumer-facing
surface for inspecting and controlling Kyle's local AI fleet (Master
Blaster + Kaydanski Ollama hosts). It is the "operator" twin of the two
inference dashboards:

- [LilBlue](./falkensteink-API-LilBlue-ReadMe.md) — Kaydanski Ollama
  proxy (RX 6600). Public inference surface, no auth on proxy routes.
- [Reaper](./falkensteink-API-Reaper-ReadMe.md) — Master Blaster Ollama
  proxy (RX 9070 XT). Public inference surface, no auth on proxy routes.
- **AI Fleet Dashboard (this doc)** — model CRUD, warm-set editing,
  inference smoke tests, NSSM env management, fleet-wide audit log.
  **BirdMug-Auth gated. Kyle only.**

For the deploy-side view (compose layout, secrets, SSH key install,
ControlMaster sockets, etc.) see
[`Birdmug-AI-Fleet-Dashboard/DEPLOY.md`](./Birdmug-AI-Fleet-Dashboard/DEPLOY.md).
This doc is the **API surface**, not the deploy guide.

## Owner

Kyle's service. Single-user by design — every write operation is
attributed to the JWT subject in the audit log, and no provisioning
exists for non-`kyle.falkenstein@…` users. Do not wire third-party
clients to this API; have them call LilBlue or Reaper directly.

## Endpoint

```text
https://ai.birdmug.com
```

This is the cloudflared-tunneled, BirdMug-Auth-gated entry. There is
no LAN-direct equivalent — the dashboard's host:port binding is
`127.0.0.1:8794` on Toshi (cloudflared-only reach).

## Authentication

**BirdMug-Auth (`birdmug_token` cookie on `.birdmug.com`).** Identical
to lilblue.birdmug.com / reaper.birdmug.com / obd.birdmug.com. Every
route — page renders and JSON APIs alike — runs through `@require_auth`.

The JWT subject is recorded on every write op (load, unload, pull,
delete, env set, restart, warm-set write, inference test). See the
audit log section below.

If you're calling from a script:

```bash
# Get a token (one-time, then cache the cookie):
# Browser → https://accounts.birdmug.com/login → store birdmug_token

curl -sS https://ai.birdmug.com/api/models/hosts \
  -H "Cookie: birdmug_token=<jwt>"
```

There is no API-key or service-account path. If a non-Kyle consumer
needs fleet visibility, the right answer is a read-only mirror of the
audit log or a Loki query, not a credential.

## Surface

The dashboard exposes three logical layers:

### 1. Page renders (HTML)

| Path | Purpose |
|---|---|
| `GET /` | Outer tabbed shell — iframes Reaper / LilBlue / OBD / Models |
| `GET /models` | Model-management page (the only tab served by this container) |

The four tabs are pure iframes carrying the user's `birdmug_token`
cookie. Each per-service tab renders its own dashboard's HTML
(no federated CSS, no copied chrome).

### 2. Host registry

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/models/hosts` | List the two control planes (`mb` + `kaydanski`) — hostnames, Ollama URLs, SSH user |

`<host>` in every model API below is one of `mb` or `kaydanski`.

### 3. Per-host model operations

These wrap Ollama's `/api/*` (HTTP, port 11434) for reads, and NSSM /
warm-set edits over SSH for control-plane writes. See
[DEPLOY.md](./Birdmug-AI-Fleet-Dashboard/DEPLOY.md) for the full
endpoint table; the consumer-relevant subset:

**Reads (Ollama HTTP):**

```text
GET    /api/models/<host>/ps        — loaded models + VRAM usage
GET    /api/models/<host>/tags      — installed model catalog
POST   /api/models/<host>/show      — model details (modelfile, params)
```

**Inference (Ollama HTTP):**

```text
POST   /api/models/<host>/load      — warm into VRAM
POST   /api/models/<host>/unload    — evict (keep_alive=0s)
POST   /api/models/<host>/test      — smoke-test inference (returns latency + token count)
POST   /api/models/<host>/pull      — pull a new tag (SSE progress)
DELETE /api/models/<host>/delete    — remove (requires {model, confirm_name: <same>})
```

**Control plane (SSH):**

```text
GET    /api/models/<host>/env             — NSSM AppEnvironmentExtra
PUT    /api/models/<host>/env             — replace NSSM env (caller must restart)
POST   /api/models/<host>/restart-ollama  — nssm restart OllamaService
GET    /api/models/<host>/warm-set        — read warm-set.json
PUT    /api/models/<host>/warm-set        — write warm-set.json
```

**Audit:**

```text
GET    /api/audit                          — last 200 write-op entries (newest-last)
```

Every write op (load, unload, pull, delete, test, env_set, restart,
warm-set write) emits one JSON line to `/data/fleet_audit.log` inside
the container, tagged with the JWT subject and a timestamp. Survives
rebuilds (named volume — see DEPLOY.md).

## Example: smoke-test a model

```bash
curl -sS https://ai.birdmug.com/api/models/mb/test \
  -H "Cookie: birdmug_token=$BIRDMUG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3:14b"}'
```

Returns `{"ok": true, "model": "qwen3:14b", "latency_ms": <int>,
"tokens": <int>}` on success; non-200 with `{ok: false, error: …}` on
failure. Always audit-logged.

## Example: read warm-set, edit it, write it back

```bash
# Read current warm-set on Kaydanski
curl -sS https://ai.birdmug.com/api/models/kaydanski/warm-set \
  -H "Cookie: birdmug_token=$BIRDMUG_TOKEN"

# -> {"chat":["qwen2.5:7b"], "embed":["bge-m3:latest"]}

# Write new warm-set
curl -sS -X PUT https://ai.birdmug.com/api/models/kaydanski/warm-set \
  -H "Cookie: birdmug_token=$BIRDMUG_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat":["qwen2.5:7b","qwen3:14b"],"embed":["bge-m3:latest"]}'
```

The warm-set file is read at boot by each host's resume / warm script
(`master-blaster-ai-control/AI-Resume.ps1` reads
`warm-set.json`; `kaydanski-ai-control/ollama-warm.ps1` reads
`ollama-warm-set.json`). Changes via this API don't take effect until
the next warm — call `POST /api/models/<host>/restart-ollama` (or
trigger an `AI-Resume`) to apply immediately.

## Service shape

| | |
|---|---|
| **Container** | `ai_fleet_dashboard` (Python/Flask + gunicorn gthread workers) |
| **Compose** | `~/AIInfrastructure/Birdmug-AI-Fleet-Dashboard/docker-compose.prod.yml` |
| **Port** | `127.0.0.1:8794:8794` (cloudflared-only — no LAN reach) |
| **Worker model** | `--worker-class gthread --workers 1 --threads 8 --timeout 120` |
| **Public URL** | `https://ai.birdmug.com/` (BirdMug-Auth, all routes) |
| **Cloudflared** | `ai_fleet_cloudflared` container, config mount `:ro` |
| **Restart policy** | `on-failure:3` (Toshi-standard) |
| **Audit volume** | named volume `ai_fleet_audit_data` → `/data` |
| **SSH ControlMaster** | `/tmp/ssh-cm` in-container — multiplexes SSH to MB + Kaydanski for snappy GUI |

Full host details: [`MASTERBLASTER.md`](./MASTERBLASTER.md),
[`KAYDANSKI.md`](./KAYDANSKI.md). Compose / secrets / SSH key install:
[`DEPLOY.md`](./Birdmug-AI-Fleet-Dashboard/DEPLOY.md).

## Topology

```text
Kyle (browser)
  -> https://ai.birdmug.com
     -> cloudflared tunnel on Toshi
     -> ai_fleet_dashboard:8794 (BirdMug-Auth)
        |
        |-- HTTP   --> http://192.168.4.33:11434     (MB Ollama: ps/tags/show/load/unload/test/pull/delete)
        |-- HTTP   --> http://kaydanskipc:11434      (Kaydanski Ollama: same)
        |-- SSH    --> Kyle@192.168.4.33             (MB control plane: nssm get/set, restart, warm-set.json)
        |-- SSH    --> Kaiden@kaydanskipc            (Kaydanski control plane: same)
        |-- WRITE  --> /data/fleet_audit.log         (every write op, JWT-attributed)
```

Inference traffic flowing through this dashboard is **not** the same as
inference traffic to LilBlue / Reaper. Smoke tests via
`/api/models/<host>/test` execute against the underlying Ollama
host directly, not via the LilBlue / Reaper proxies — so they will not
appear in those dashboards' traffic tables. They will appear in
`/api/audit`.

## Relationship to the inference dashboards

This service is purely **additive**. Killing this container does not
take down LilBlue, Reaper, or OBD — the per-service inference paths are
independent. What you lose:

- The unified MODELS view (you can still drive Ollama directly per host
  via SSH or LAN HTTP).
- The warm-set editor (edit `warm-set.json` / `ollama-warm-set.json`
  directly on each host).
- The fleet-wide audit log.

Day-to-day inference is unaffected.

## Security notes

- All routes require `@require_auth`. There is no escape hatch — even
  `/health` returns 200 unauthenticated only because it's a watchdog
  probe with no host context.
- Write ops require the JWT subject to match Kyle's email (enforced
  by BirdMug-Auth issuance — there's no separate authz layer in this
  service).
- SSH from the container uses a dedicated key
  (`toshi-falkensteink-fleet-dashboard`) restricted by `from=` clause
  to Toshi's tailnet + LAN IPs on both target hosts. See
  [DEPLOY.md](./Birdmug-AI-Fleet-Dashboard/DEPLOY.md) → "One-time SSH
  key authorization" for the install procedure + key rotation.
- Audit log is **append-only by convention** (not enforced — Kyle on
  Toshi can truncate the volume). Loki ships it for off-host retention.
