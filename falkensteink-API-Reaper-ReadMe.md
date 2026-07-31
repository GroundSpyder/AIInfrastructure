# Reaper API

Reaper is Kyle's primary 14b chat-quality inference node. The Ollama runtime
lives on Master Blaster (Kyle's main dev PC, RX 9070 XT 16 GB VRAM); a proxy +
dashboard ("Birdmug-Reaper-Dashboard") runs on Toshi and exposes the same
surface plus live metrics.

Reaper speaks Ollama's full API — embeddings, chat, generate, and
OpenAI-compatible `/v1` — with no authentication required on the proxy
routes (tailnet / LAN membership is the boundary). It is the MB-side twin
of [LilBlue](./falkensteink-API-LilBlue-ReadMe.md), which proxies Kaydanski.

## Owner

Reaper is Kyle's service. Master Blaster is Kyle's primary dev PC, so unlike
LilBlue (a polite boarder on Kaiden's gaming rig) Reaper has the host largely
to itself. Heavy daytime Claude Code usage on MB still competes for CPU and
the GPU is gaming-shared on weekends/evenings — see the gaming-courtesy
section below.

## Endpoints

Two ways to reach Reaper. Same model catalog (the Toshi proxy forwards to
the same Ollama runtime), differing in network reachability and side
effects.

### A. Toshi proxy (preferred for new integrations)

```text
http://192.168.4.31:8793
```

This is the `reaper_dashboard` container on Toshi. Every request through
it is recorded in the metrics tracker and visible at
`https://reaper.birdmug.com/` — the dashboard's "Recent Reaper Traffic"
table, latest perf card, and 5-min / 1-h counter windows. **Use this
endpoint when you want your traffic to be observable.**

Reachable from:
- Any host on the home LAN (`192.168.4.x`)
- Containers on Toshi (use Tailscale IP or `host.docker.internal` from
  within the same compose network when bridged)
- Master Blaster itself (cross-machine round trip — adds a few ms but
  populates metrics)

Not reachable from the public internet — port 8793 is LAN-bound. The
dashboard root at `https://reaper.birdmug.com/` is behind BirdMug-Auth;
the proxy routes (`/v1/*`, `/api/*`) are intentionally unauthenticated.

### B. Direct Ollama on Master Blaster

```text
http://masterblaster:11434          # tailnet hostname (MagicDNS)
http://100.99.122.75:11434          # tailnet IP, fallback if MagicDNS fails
http://192.168.4.33:11434           # LAN IP, fallback if Tailscale is paused
```

This is the underlying `ollama.exe serve` NSSM service. Use this when:
- The caller is itself on Master Blaster and you want to avoid any
  network round-trip.
- You want to bypass the proxy entirely for low-latency debugging.

Direct Ollama traffic does **not** show up in the Reaper dashboard.

## Authentication

None on either endpoint surface for inference traffic. The boundaries are:
- **Toshi proxy:** LAN-only port binding (UFW inactive, but no public
  tunnel exposes `:8793`)
- **Direct Ollama:** tailnet membership + Windows Firewall blocking the
  public profile

If a future requirement opens a public path, add auth at the new layer.
Don't rely on `@require_auth` on the proxy routes — they deliberately omit
it so non-JWT clients (ops-rag, n8n, etc.) can call them.

## Models

| Model | Purpose | VRAM | Speed |
|---|---|---|---|
| `qwen3:14b` | Chat-quality narrative, coach review, longer reasoning | ~10.3 GB | ~52 tok/sec (ROCm GPU) |
| `bge-m3` | Embeddings | ~1.2 GB | ~20 embeds/sec (ROCm GPU) |

Warm set total: ~11.5 GB / 16 GB VRAM resident. Headroom for one
additional small model if needed (`OLLAMA_MAX_LOADED_MODELS=2`).

GPU: AMD Radeon RX 9070 XT (RDNA 4, gfx1201, 16 GB VRAM). ROCm 7.2.1 via
HIP SDK 6.4 (`ROCBLAS_TENSILE_LIBPATH=C:\Program Files\AMD\ROCm\6.4\bin\rocblas\library`).
Per MB benchmarks, ROCm is +9–67% faster than Vulkan on this card depending
on the model.

## Supported Routes

The Toshi proxy implements these routes (all forward to Ollama, all
tracked in the dashboard metrics):

### Ollama-native (proxied + tracked)

```text
POST /api/generate     — raw completion, supports stream
POST /api/chat         — chat completion, supports stream
POST /api/embed        — batch embeddings
POST /api/embeddings   — legacy single-text embedding
```

Stream support honors the client's `"stream": true|false` field. Ollama's
default for `/api/generate` and `/api/chat` is streaming; the proxy
passes that through.

### OpenAI-compatible (proxied + tracked)

```text
POST /v1/chat/completions
GET  /v1/models
```

For OpenAI-compatible clients, pass any non-empty string as the API key —
Ollama and the proxy both ignore it:

```text
Authorization: Bearer ollama
```

### Direct-only (no proxy, hit Ollama directly)

```text
GET  /api/ps           — loaded models + VRAM usage
GET  /api/tags         — model catalog
```

These are not proxied. The dashboard's status panel calls them
server-side via the internal `server/reaper.py` client. If you need them
from outside Toshi, hit Ollama directly on Master Blaster.

### Gate endpoints (added 2026-07-30)

```text
POST /api/gate         — heartbeat receiver (Master Blaster's watcher posts here)
GET  /api/node-health   — liveness view shaped for Uptime Kuma
```

`GET /api/node-health` is **unauthenticated** and returns:

- **200** when the node is usable **or deliberately away for gaming**
- **503** only when it is genuinely unreachable with no explanation

```json
{ "node": "master-blaster", "status": "up|away|down",
  "gate": { "state": "available|paused", "game": "...", "age_seconds": 1.5 } }
```

Point uptime checks here rather than at Ollama's port directly — otherwise
the monitor goes red for the whole of every gaming session.

`POST /api/gate` is also unauthenticated (LAN-bound, same rationale as the
proxy routes) and carries no secrets. It exists because a refused connection
alone cannot distinguish "gated for gaming" from "PSU died".

## Environment config

### Toshi proxy clients (preferred for observability)

```
OLLAMA_URL=http://192.168.4.31:8793
```

Or for OpenAI-compatible clients:

```
OPENAI_BASE_URL=http://192.168.4.31:8793/v1
OPENAI_API_KEY=ollama
```

### Direct Ollama clients

```
OLLAMA_URL=http://masterblaster:11434
```

Or:

```
OPENAI_BASE_URL=http://masterblaster:11434/v1
OPENAI_API_KEY=ollama
```

## Recommended `keep_alive`

**This matters less than on Kaydanski/LilBlue** because MB has more VRAM
headroom, but the warm set is sized to stay loaded. Don't override
unless you have a reason.

| Use case | `keep_alive` | Reason |
|---|---|---|
| Chat / one-off query | `30m` (default) | qwen3:14b stays warm — keeps the warm set predictable. |
| Bulk embeddings (backfill, reindex) | `30m` | bge-m3 (1.2 GB) is small. Leave warm. |
| Gaming-imminent (close to BG3 session) | `0s` | Releases VRAM immediately; Kyle's `AI-Pause.cmd` on MB hard-unloads everything regardless of `keep_alive`. |

## Example Requests

These work against either endpoint — swap `192.168.4.31:8793` for
`masterblaster:11434` to bypass the proxy.

List loaded models (direct only — `/api/ps` is not proxied):

```bash
curl http://masterblaster:11434/api/ps
```

Chat completion (Ollama-native, through Toshi proxy):

```bash
curl -s http://192.168.4.31:8793/api/chat \
  -d '{
    "model": "qwen3:14b",
    "messages": [{"role": "user", "content": "Reply exactly: Reaper ready"}],
    "stream": false
  }'
```

Embeddings (through Toshi proxy):

```bash
curl -s http://192.168.4.31:8793/api/embed \
  -d '{"model": "bge-m3", "input": ["hello world"]}'
```

Chat completion (OpenAI-compatible, through Toshi proxy):

```bash
curl -s http://192.168.4.31:8793/v1/chat/completions \
  -H "Authorization: Bearer ollama" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3:14b",
    "messages": [{"role": "user", "content": "Reply exactly: Reaper ready"}],
    "max_tokens": 10
  }'
```

## Service Shape (Ollama on Master Blaster)

| | |
|---|---|
| **Process** | `ollama.exe serve` |
| **NSSM service** | `OllamaService` — AUTO_START, LocalSystem, restart-on-exit (2s delay) |
| **Port** | `11434` (TCP) bound to `0.0.0.0` |
| **Priority** | BelowNormal — yields to games / Claude Code |
| **Max loaded models** | 2 (`OLLAMA_MAX_LOADED_MODELS=2`) — fits the warm set |
| **Keep-alive default** | 30m (overridden per-call — see table above) |
| **Backend** | ROCm via HIP SDK 6.4 (`ROCBLAS_TENSILE_LIBPATH` env var) |
| **Logs** | `C:\Users\kylej\ollama-logs\service-stdout.log` / `service-stderr.log` (10 MB rotation) |

Full host details in [`MASTERBLASTER.md`](../MASTERBLASTER.md).

## Service Shape (Reaper dashboard + proxy on Toshi)

| | |
|---|---|
| **Container** | `reaper_dashboard` (Python/Flask + gunicorn gthread workers) |
| **Compose** | `~/AIInfrastructure/Birdmug-Reaper-Dashboard/docker-compose.prod.yml` |
| **Port** | `0.0.0.0:8793:8793` (LAN-bound) |
| **Worker model** | `--worker-class gthread --workers 1 --threads 8 --timeout 660` |
| **Memory cap** | 256 M |
| **Public URL** | `https://reaper.birdmug.com/` (BirdMug-Auth, dashboard only) |
| **Cloudflared** | `reaper_cloudflared` container, no shell healthcheck (distroless image) |
| **Restart policy** | `on-failure:3` (Toshi-standard) |

## Start and Stop

**Normally you do nothing.** Since 2026-07-30 a SYSTEM scheduled task
(`Falkensteink-GameWatch`) on Master Blaster stops `OllamaService` whenever a
watched game process is running, and restarts + re-warms it ~60 s after the
game exits. `OllamaService` is also `StartType=Manual` now, so a reboot cannot
un-gate the card.

Manual overrides remain (desktop shortcuts):

```
Ctrl+Alt+P  / AI-Pause.cmd    — STOP the service (sticky; outranks the watcher)
Ctrl+Alt+R  / AI-Resume.cmd   — start + warm; refuses while a game is running
```

> **These now stop and start the service, not just unload models.** The old
> `keep_alive=0` unload could not hold: the fleet gateway load-balances
> `fleet/embed` onto this box and routes all of `fleet/chat-quality` here, so
> ordinary background traffic pulled ~9-11 GB straight back into VRAM within
> minutes, mid-game. A stopped service refuses connections, which also lets the
> gateway cool this backend down and fail over cleanly.

Check state at any time:

```powershell
.\Game-Watch.ps1 -Status        # gate state, service state, API reachability
.\Game-Watch.ps1 -Candidates    # find a new game's process name to add
```

Watchlist is `games.json` in `master-blaster-ai-control\`, re-read every poll.
Full detail: [`master-blaster-ai-control/README.md`](./master-blaster-ai-control/README.md).

Service management (admin shell on MB):

```powershell
sc query OllamaService                       # state check
nssm restart OllamaService                   # after config changes
nssm get OllamaService AppEnvironmentExtra   # inspect env vars
```

Pull a new model:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull <model-name>
```

Toshi-side proxy management (`ssh falkensteink@192.168.4.31`):

```bash
docker logs reaper_dashboard --tail 100
docker compose -f ~/AIInfrastructure/Birdmug-Reaper-Dashboard/docker-compose.prod.yml restart reaper-dashboard
```

## Gaming Courtesy

Master Blaster is Kyle's primary dev PC and the GPU is gaming-shared.

- Ollama runs at **BelowNormal** CPU priority so Claude Code / games / the
  desktop stay responsive.
- The warm set is `qwen3:14b` + `bge-m3` ≈ **11.5 GB of 16 GB**. There is *not*
  room to game with it loaded — which is why the gate is all-or-nothing rather
  than a smaller always-on footprint.
- **This is now automatic.** `Falkensteink-GameWatch` stops the service when a
  watched game starts and restores it after. You should not need to remember
  the hotkey. Every uncertain path in that watcher fails toward *gaming*: an
  unreadable watchlist, a failed poll, or a dead watcher all leave Ollama
  stopped.
- **Reaper being unreachable during gaming hours is expected, not an outage.**
  Do not "fix" it, and do not page on it — use `GET /api/node-health`, which
  returns 200 for `away` and 503 only for a genuine fault.
- If Master Blaster is unreachable, callers should fall back gracefully.
  Do not retry-loop into Reaper from a tight loop — fall back to LilBlue
  (qwen2.5:7b on Kaydanski) for chat or queue the request.

> **Consumer note — Windows does not refuse, it hangs.** A gated Master Blaster
> drops packets rather than sending a TCP reset, so a naive client waits for its
> full timeout instead of failing fast. Measured 2026-07-30: an embed request
> through the gateway never returned inside 90 s. The proxy now short-circuits
> on the gate heartbeat and answers **503 in ~1 ms** instead. If you talk to
> Ollama on Master Blaster *directly*, set a short connect timeout yourself —
> you do not get that protection.

## Topology

```text
Kyle's services (Toshi / local / cross-host)
  -> http://192.168.4.31:8793          (LAN -> Toshi proxy + dashboard tracking)
     -> http://192.168.4.33:11434      (LAN -> Ollama runtime on MB)
        -> OllamaService (NSSM)
        -> ollama.exe serve
        -> AMD RX 9070 XT (ROCm) / CPU fallback for oversized models

  -- OR --

  -> http://masterblaster:11434        (direct, untracked)
  -> OllamaService (NSSM)
  -> ollama.exe serve
```

Ollama is NOT directly public-facing. Everything that needs public
inference goes through an authenticated layer (a project's own API,
Kyle-Rag, etc.).

## Reaper vs LilBlue — which one to use

| Need | Route to | Why |
|---|---|---|
| 14b-class chat quality, long context | **Reaper** (qwen3:14b on 9070 XT) | More VRAM, faster, better model. |
| 7b chat (cheap, conversational) | LilBlue (qwen2.5:7b on RX 6600) | Adequate quality, doesn't need Reaper's headroom. |
| Embeddings | Either — both run bge-m3 | Pick by proximity to the caller. |
| Vision / OCR | LilBlue (CPU-only via Vulkan limitation) | Reaper hasn't been benchmarked for vision yet. |
| Anything during MB gaming | LilBlue | MB GPU may be paused for the game. |
| Anything during Kaiden gaming | Reaper | Kaydanski GPU may be paused. |

The eventual [ollama-gateway](https://github.com/falkensteink/ollama-gateway)
revival should hide this choice behind logical roles
(`fleet/chat-quality` → Reaper, `fleet/chat-cheap` → LilBlue) — until
then, consumers pick the endpoint directly.

## Troubleshooting

| Symptom | First check |
|---|---|
| Connection refused on 11434 | Is `OllamaService` running on MB? `sc query OllamaService`. Did AI-Pause stop it? `AI-Resume.cmd` to bring it back. |
| Connection refused on 8793 | Is `reaper_dashboard` container up on Toshi? `ssh falkensteink@192.168.4.31 'docker ps | grep reaper'`. Logs: `docker logs reaper_dashboard --tail 100`. |
| Inference painfully slow / 100% CPU | Is ROCm active? Watch for ollama#13920 silent CPU fallback. `Verify-GPU.ps1` on MB catches it — confirms `/api/ps` shows VRAM-loaded models AND a 50-tok chat hits ≥20 tok/sec floor. |
| bge-m3 embedding times out | Concurrent chat model is loaded and VRAM is saturated. Wait for the chat call's `keep_alive` to expire, then retry. |
| Dashboard shows no traffic but Ollama is up | Caller is hitting `masterblaster:11434` directly. Repoint to `192.168.4.31:8793` to populate metrics. |
| Embed requests block other traffic on the proxy | Was the worker model reverted to sync? Check `Dockerfile.prod` CMD — must be `--worker-class gthread --threads 8`. |
| Machine unreachable overnight | Sleep timeout re-set by Windows update. On MB: `powercfg /change standby-timeout-ac 0`. |

## Security Notes

- `masterblaster` and `100.99.122.75` are tailnet addresses — not reachable
  from the public internet.
- `192.168.4.33` and `192.168.4.31:8793` are LAN-only (UFW inactive on
  Toshi, but no public tunnel exposes the port).
- Ollama has **no bearer token**. The Toshi proxy's inference routes also
  have no bearer token — they intentionally don't use `@require_auth` so
  non-JWT clients can call them.
- Do not expose port 11434 or 8793 through a public tunnel without adding
  an authenticated proxy in front of them first.
