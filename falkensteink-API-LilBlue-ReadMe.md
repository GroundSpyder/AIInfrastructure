# LilBlue API

LilBlue is Kyle's shared local AI inference node. The Ollama runtime lives on
Kaydanski (Kaiden's gaming PC on the home tailnet); a proxy + dashboard
("Birdmug-LilBlue-Dashboard") runs on Toshi and exposes the same surface
plus live metrics.

LilBlue speaks Ollama's full API — embeddings, chat, generate, and
OpenAI-compatible `/v1` — with no authentication required (tailnet / LAN
membership is the boundary).

## Owner

LilBlue is Kyle's service. Kaiden owns the underlying hardware on Kaydanski;
LilBlue is a polite boarder. Do not assume exclusive use — Kaiden games on
the host. See gaming-courtesy rules below.

## Endpoints

There are now **two ways** to reach LilBlue. They share the same model
catalog (the Toshi proxy forwards to the same Ollama runtime), but differ
in network reachability and side effects.

### A. Toshi proxy (preferred for new integrations)

```text
http://192.168.4.31:8792
```

This is the `lilblue-dashboard` container on Toshi. Every request through
it is recorded in the metrics tracker and visible at
`https://lilblue.birdmug.com/` — the dashboard's "Recent LilBlue Traffic"
table, latest perf card, and 5-min / 1-h counter windows. **Use this
endpoint when you want your traffic to be observable.**

Reachable from:
- Any host on the home LAN (`192.168.4.x`)
- Containers on Toshi (use Tailscale IP or `host.docker.internal` from
  within the same compose network when bridged)
- Kaydanski / Kaydanski Docker containers (LAN reach)

Not reachable from the public internet — port 8792 is LAN-bound. The
dashboard root at `https://lilblue.birdmug.com/` is behind BirdMug-Auth;
the proxy routes (`/v1/*`, `/api/*`) are intentionally unauthenticated.

### B. Direct Ollama on Kaydanski

```text
http://kaydanskipc:11434          # tailnet hostname
http://100.83.51.117:11434        # tailnet IP, fallback if MagicDNS fails
```

This is the underlying `ollama.exe serve` NSSM service. Use this when:
- The caller is itself on Kaydanski and you want to avoid a Tailscale
  round-trip (e.g. Kyle-Rag work instance — see "Kyle-Rag routing" below).
- The caller is a Docker container on Kaydanski — use
  `http://host.docker.internal:11434` for in-host reach without going
  through Tailscale.
- You want to bypass the proxy entirely for low-latency debugging.

Direct Ollama traffic does **not** show up in the LilBlue dashboard.

## Kyle-Rag routing

As of this session (2026-05-12), the Kyle-Rag **personal** instance on
Kaydanski routes all Ollama calls through the Toshi proxy:

```
KYLE_RAG_OLLAMA_URL=http://192.168.4.31:8792
KYLE_RAG_EMBEDDING_OLLAMA_URL=http://192.168.4.31:8792
```

Path: Kyle-Rag (Kaydanski Docker) → Toshi:8792 (proxy) → kaydanskipc:11434
(Ollama). This is a deliberate cross-machine round trip — adds a few ms per
call but makes every embed and chat visible in the LilBlue dashboard
traffic table.

Kyle-Rag **work** (`kyle_rag_work_*` containers on Kaydanski) still points
at `http://host.docker.internal:11434` — direct, not proxied. That instance
is not migrated yet.

## Authentication

None on either endpoint surface for inference traffic. The boundaries are:
- **Toshi proxy:** LAN-only port binding (UFW inactive, but no public
  tunnel exposes `:8792`)
- **Direct Ollama:** tailnet membership + Windows Firewall blocking the
  public profile

If a future requirement opens a public path, add auth at the new layer.
Don't rely on `@require_auth` on the proxy routes — they deliberately omit
it so non-JWT clients (Kyle-Rag, ops-rag, n8n) can call them.

## Models

| Model | Purpose | VRAM | Speed |
|---|---|---|---|
| `bge-m3` | Embeddings (Kyle-Rag + corpus ingestion) | ~1.2 GB | ~16 embeds/sec (Vulkan GPU) |
| `qwen2.5:7b` | Fast chat, intent classification, tagging | ~5 GB | ~30 tok/sec (Vulkan GPU) |
| `qwen3:30b-a3b` | High-quality chat (MoE, CPU-only — too large for 8 GB VRAM) | 18.5 GB RAM | slower, CPU |
| `qwen3:30b-a3b-cpu` | Same MoE weights, CPU-pinned via Modelfile (won't evict GPU residents) | 19.5 GB RAM | slower, CPU |

GPU: AMD RX 6600 (RDNA2, 8 GB VRAM). Vulkan backend active via
`OLLAMA_VULKAN=1` + `OLLAMA_LLM_LIBRARY=vulkan`.

## Supported Routes

The Toshi proxy implements these routes (all forward to Ollama, all
tracked in the dashboard metrics):

### Ollama-native (proxied + tracked)

```text
POST /api/generate     — raw completion, supports stream
POST /api/chat         — chat completion, supports stream
POST /api/embed        — batch embeddings (used by Kyle-Rag)
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

These are not proxied today. The dashboard's status panel calls them
server-side via the internal `server/lilblue.py` client. If you need them
from outside Toshi, hit Ollama directly on Kaydanski.

## Environment config

### Toshi proxy clients (preferred for observability)

```
OLLAMA_URL=http://192.168.4.31:8792
```

Or for OpenAI-compatible clients:

```
OPENAI_BASE_URL=http://192.168.4.31:8792/v1
OPENAI_API_KEY=ollama
```

### Direct Ollama clients

```
OLLAMA_URL=http://kaydanskipc:11434
```

Or:

```
OPENAI_BASE_URL=http://kaydanskipc:11434/v1
OPENAI_API_KEY=ollama
```

From a Docker container *on Kaydanski*, prefer:

```
OLLAMA_URL=http://host.docker.internal:11434
```

— Docker Desktop's host alias avoids a Tailscale loopback.

## Recommended `keep_alive`

**This matters.** Loaded models sit in Kaiden's gaming GPU VRAM.

| Use case | `keep_alive` | Reason |
|---|---|---|
| Chat / one-off query | `0s` | qwen2.5:7b is 5 GB. Release VRAM immediately — don't hold the GPU between calls. |
| Bulk embeddings (backfill, reindex) | `5m`–`30m` | Avoids reload penalty between bursts. bge-m3 (1.2 GB) is small enough to leave warm. |

## Example Requests

These work against either endpoint — swap `192.168.4.31:8792` for
`kaydanskipc:11434` to bypass the proxy.

List loaded models (direct only — `/api/ps` is not proxied):

```bash
curl http://kaydanskipc:11434/api/ps
```

Chat completion (Ollama-native, through Toshi proxy):

```bash
curl -s http://192.168.4.31:8792/api/chat \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Reply exactly: LilBlue ready"}],
    "stream": false,
    "keep_alive": "0s"
  }'
```

Embeddings (through Toshi proxy):

```bash
curl -s http://192.168.4.31:8792/api/embed \
  -d '{"model": "bge-m3", "input": ["hello world"]}'
```

Chat completion (OpenAI-compatible, through Toshi proxy):

```bash
curl -s http://192.168.4.31:8792/v1/chat/completions \
  -H "Authorization: Bearer ollama" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Reply exactly: LilBlue ready"}],
    "max_tokens": 10
  }'
```

## Service Shape (Ollama on Kaydanski)

| | |
|---|---|
| **Process** | `ollama.exe serve` |
| **NSSM service** | `OllamaService` — AUTO_START, LocalSystem, restart-on-exit (2s delay) |
| **Port** | `11434` (TCP) bound to `0.0.0.0` |
| **Priority** | BelowNormal — yields to games |
| **Max loaded models** | 1 at a time (`OLLAMA_MAX_LOADED_MODELS=1`) — see AI_FLEET_STRATEGY.md note that this may be 4 in current config |
| **Keep-alive default** | 30m (overridden per-call — see table above) |
| **Logs** | `C:\Users\Kaiden\ollama-logs\service-stdout.log` / `service-stderr.log` (10 MB rotation) |

## Service Shape (LilBlue dashboard + proxy on Toshi)

| | |
|---|---|
| **Container** | `lilblue_dashboard` (Python/Flask + gunicorn gthread workers) |
| **Compose** | `~/AIInfrastructure/Birdmug-LilBlue-Dashboard/docker-compose.prod.yml` |
| **Port** | `0.0.0.0:8792:8792` (LAN-bound) |
| **Worker model** | `--worker-class gthread --workers 1 --threads 8 --timeout 360` |
| **Memory cap** | 256 M (bumped from 128 M to accommodate 8 threads) |
| **Public URL** | `https://lilblue.birdmug.com/` (BirdMug-Auth, dashboard only) |
| **Cloudflared** | `lilblue_cloudflared` container, healthcheck uses `curl -sf` (no `wget` in image) |
| **Restart policy** | `on-failure:3` (Toshi-standard) |

## Start and Stop

Start/stop by Kaiden (desktop):

```
AI-Pause.cmd    — stops Ollama entirely (releases GPU for gaming)
AI-Resume.cmd   — restarts Ollama
```

Service management (admin shell over SSH):

```powershell
sc query OllamaService              # state check
nssm restart OllamaService          # after config changes
nssm get OllamaService AppEnvironmentExtra   # inspect env vars
```

Pull a new model (SSH-safe — no WCM needed for Ollama registry):

```bash
ssh Kaiden@kaydanskipc 'powershell -Command "& \"$env:LOCALAPPDATA\Programs\Ollama\ollama.exe\" pull <model-name>"'
```

Toshi-side proxy management (`ssh falkensteink@192.168.4.31`):

```bash
docker logs lilblue_dashboard --tail 100
docker compose -f ~/AIInfrastructure/Birdmug-LilBlue-Dashboard/docker-compose.prod.yml restart lilblue-dashboard
```

## Gaming Courtesy

Kaiden plays games on this machine. LilBlue is a polite boarder.

- Ollama runs at **BelowNormal** CPU priority.
- Any loaded chat model sits in Kaiden's gaming GPU VRAM. `keep_alive=0s` on every chat call is **mandatory** — not optional.
- `AI-Pause.cmd` on Kaiden's desktop hard-stops Ollama and fully releases the GPU. If LilBlue goes unreachable around gaming hours, he may have paused it — this is expected and fine.
- If Kaydanski is unreachable, callers should fall back gracefully. Do not retry-loop into Kaydanski from a tight loop.

## Topology

```text
Kyle's services (Toshi / local / Kaydanski Docker)
  -> http://192.168.4.31:8792          (LAN -> Toshi proxy + dashboard tracking)
     -> http://kaydanskipc:11434       (tailnet -> Ollama runtime)
        -> OllamaService (NSSM)
        -> ollama.exe serve
        -> AMD RX 6600 (Vulkan) / CPU fallback for oversized models

  -- OR --

  -> http://kaydanskipc:11434          (direct, untracked)
  -> OllamaService (NSSM)
  -> ollama.exe serve
```

Kyle-Rag (public-facing RAG):

```text
https://ik.birdmug.com
  -> cloudflared tunnel on Toshi
  -> kaydanskipc:8030 (Kyle-Rag personal IK, Docker)
  -> http://192.168.4.31:8792 (LilBlue proxy on Toshi)
  -> http://kaydanskipc:11434 (Ollama on Kaydanski)
```

Ollama is NOT directly public-facing. Everything that needs public inference goes through an authenticated layer (Kyle-Rag, or a project's own API).

## Troubleshooting

| Symptom | First check |
|---|---|
| Connection refused on 11434 | Is `OllamaService` running? `sc query OllamaService`. Did Kaiden pause it? `AI-Pause.cmd` stops it. |
| Connection refused on 8792 | Is `lilblue_dashboard` container up on Toshi? `ssh falkensteink@192.168.4.31 'docker ps | grep lilblue'`. Compose logs: `docker logs lilblue_dashboard --tail 100`. |
| Inference painfully slow | Check `GET /api/ps` (direct, kaydanskipc:11434) — is Vulkan active? Service-stdout.log should show `ggml_vulkan: Found 1 Vulkan devices` on startup. If missing, `OLLAMA_VULKAN=1` may have been dropped from NSSM env. |
| bge-m3 embedding times out | Concurrent chat model is loaded and VRAM is saturated. Wait for the chat call to finish (and its keep_alive to expire), then retry. |
| Dashboard shows no traffic but Ollama is up | Caller is hitting `kaydanskipc:11434` directly. Repoint to `192.168.4.31:8792` to populate metrics. |
| Embed requests block other traffic on the proxy | Was the worker model reverted to sync? Check `Dockerfile.prod` CMD — must be `--worker-class gthread --threads 8`. |
| `docker pull` / `git push` fails over SSH | WCM gotcha — see KAYDANSKI.md "Windows Credential Manager gotcha." Has nothing to do with Ollama. |
| Machine unreachable overnight | Sleep timeout re-set by Windows update. Run: `powercfg /change standby-timeout-ac 0` on Kaydanski. |

## Security Notes

- `kaydanskipc` and `100.83.51.117` are tailnet addresses — not reachable from the public internet.
- `192.168.4.31:8792` is LAN-only (UFW inactive on Toshi, but no public tunnel exposes the port).
- Ollama has **no bearer token**. The Toshi proxy's inference routes also have no bearer token — they intentionally don't use `@require_auth` so non-JWT clients (Kyle-Rag, ops-rag, n8n) can call them.
- Do not expose port 11434 or 8792 through a public tunnel without adding an authenticated proxy in front of them first.
