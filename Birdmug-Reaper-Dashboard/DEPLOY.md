# Reaper Dashboard — Toshi Deploy Notes

Reaper is both a dashboard *and* an Ollama proxy for Master Blaster's 9070-XT
node. The dashboard at `https://reaper.birdmug.com/` (BirdMug-Auth protected)
shows live traffic, model status, and recent generation metrics. The proxy
routes — `/v1/*` and `/api/*` — forward unauthenticated to Ollama on Master
Blaster and are reachable from the LAN at `http://192.168.4.31:8793`. Tracker
metrics from the proxy populate the dashboard's traffic table.

Reaper is the MB-side twin of LilBlue (which proxies Kaydanski). Same code
shape, different upstream + different port + different brand.

## One-time Toshi setup

```bash
# Create tunnel
cloudflared tunnel create reaper
# Note the returned tunnel ID — paste it into the config below.

# Fix credentials permissions (cloudflared writes 400, needs 644)
chmod 644 ~/.cloudflared/<reaper-tunnel-id>.json

# Write config — note: bridge networking so use container name, NOT localhost
cat > ~/.cloudflared/reaper-config.yml << 'EOF'
tunnel: <reaper-tunnel-id>
credentials-file: /etc/cloudflared/<reaper-tunnel-id>.json

ingress:
  - hostname: reaper.birdmug.com
    service: http://reaper_dashboard:8793
  - service: http_status:404
EOF

# Register DNS
cloudflared tunnel route dns reaper reaper.birdmug.com
```

## Deploy / redeploy

```bash
cd ~/AIInfrastructure/Birdmug-Reaper-Dashboard
git pull
flock -w 600 /tmp/toshi-deploy.lock \
  doppler run --project birdmug-services --config prd -- \
  docker compose -f docker-compose.prod.yml up -d --build
```

Preferably register Reaper in `~/toshi-infra/deploy/deploy.sh` and let that
script handle the flock + doppler-injection — that's the supported path for
new services per `TOSHI.md` "Every Toshi-deployed service MUST be in
deploy.sh". Required entries:

| Map | Value |
|---|---|
| `REPO_DIR_FOR_BRANCH` and `REPO_DIR` | `$HOME/AIInfrastructure` |
| `COMPOSE_SUBDIR` | `Birdmug-Reaper-Dashboard` |
| `COMPOSE_FILE_MAP` | `docker-compose.prod.yml` |
| `DOPPLER_PROJECT` | `birdmug-services` |
| `HEALTH_ENDPOINTS` | `reaper_dashboard:8793:/health` |
| toshi-bot `REPO_MAP` | `"AIInfrastructure": "<deploy.sh-key>"` (already wired — LilBlue lives in the same repo) |

Note: AIInfrastructure already contains LilBlue, master-blaster-ai-control,
and orthos-comm — a single push to that repo currently triggers
LilBlue's deploy via toshi-bot. Adding Reaper means the same push will
deploy *both* dashboards. Confirm that's acceptable (it is — both are
proxy services with small build footprints; serial flock guarantees no
concurrent rebuild). If not, split `Birdmug-Reaper-Dashboard` to its
own repo and re-wire toshi-bot accordingly.

## Secrets (Doppler project: birdmug-services)

- `BIRDMUG_JWT_SECRET` — shared, already present
- `BUG_FAIRY_API_KEY` — shared, already present
- `BIRDMUG_AUTH_URL` — shared, already present
- `OLLAMA_URL` — defaults to `http://192.168.4.33:11434`, override in Doppler
  if MB changes IP or you want to proxy a different upstream
- `REAPER_TEST_MODEL` — defaults to `qwen3:14b`

## Port binding and LAN exposure

The `reaper-dashboard` container publishes its port to `0.0.0.0:8793:8793`
(not `127.0.0.1`). This is intentional so LAN clients can reach the proxy
at `http://192.168.4.31:8793`. UFW is inactive on Toshi, so the LAN-binding
alone makes the port reachable from any host on the local network.

The dashboard root (`/`) and the `/api/status` + `/api/test` endpoints stay
behind BirdMug-Auth. The proxy routes (`/v1/*`, `/api/generate`,
`/api/chat`, `/api/embed`, `/api/embeddings`, `/v1/models`) are intentionally
**unauthenticated** — same boundary as LilBlue. Clients like Kyle-Rag,
ops-rag-server, and n8n workflows don't pass JWTs; LAN membership is the
access control.

If a future requirement adds a public-internet path to the proxy routes,
add auth at that layer (cloudflared service token, reverse proxy bearer
check) — do NOT rely on the dashboard's `@require_auth` since the proxy
endpoints deliberately don't use it.

## Gunicorn worker model

The Dockerfile.prod CMD pins:

```
gunicorn --bind 0.0.0.0:8793 \
  --worker-class gthread --workers 1 --threads 8 --timeout 660 \
  --graceful-timeout 60 server.app:app
```

Same model as LilBlue post-2026-05-12. The in-memory `MetricsTracker`
singleton in `server/tracker.py` must stay shared across all requests, so
`workers=1`. Eight threads serve concurrent embed bursts without blocking
chat or dashboard pollers. Long timeout (660s) tolerates slow chat
generations on `qwen3:14b` with large contexts.

If you bump `--threads`, also bump `memory:` in `docker-compose.prod.yml`
(currently 256 M).

## Cloudflared healthcheck

The cloudflared service has **no shell-level healthcheck** — the
`cloudflare/cloudflared:2026.3.0` image is distroless (no sh/curl/wget),
so any CMD-shell probe exits 127 and false-fails. The cloudflared binary
self-monitors and reconnects on its own; `restart: on-failure:3` handles
crashes. Don't add a `healthcheck:` block back without first confirming
the image still ships a usable probe binary.

## Network note

Reaper uses **bridge networking** (`reaper_net`). The cloudflared service
reaches the app container via `http://reaper_dashboard:8793` (container
DNS name). Do NOT use `localhost:8793` — that resolves to the cloudflared
container's own loopback.

## Adding Uptime Kuma monitor

Per FRAMEWORKS.md "every public-facing service has external HTTP probe",
add a Kuma monitor against `https://reaper.birdmug.com/health` (no auth
on `/health`, returns 200 with `{"status":"ok"}`). Internal-green +
external-broken is the failure mode this catches.

## Pairing with Master Blaster

Reaper proxies whatever Ollama is running on MB. If Ollama on MB is
paused (`Ctrl+Alt+P` desktop shortcut, or `Stop-Service OllamaService`),
Reaper's `/api/status` will report `down` and the dashboard alert turns
red. Callers should fall back gracefully — don't retry-loop into Reaper
when MB is paused for gaming.

See [`MASTERBLASTER.md`](../../MASTERBLASTER.md) for the upstream service
shape, NSSM config, and ROCm env vars on MB. The Reaper container does
not own that runtime — it just forwards traffic to it.
