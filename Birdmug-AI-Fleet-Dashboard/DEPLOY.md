# AI Fleet Dashboard — Toshi Deploy Notes

The AI Fleet Dashboard is a *federating* dashboard. It does not own model
state, traffic metrics, or proxy routes — those still live in the three
per-service dashboards (LilBlue, OBD, Reaper). This service is a pure HTTP
forwarder + tabbed UI:

```
   browser  ─►  ai.birdmug.com  ─►  ai_fleet_dashboard
                                       │
                                       ├── /api/status?backend=reaper   → http://192.168.4.31:8793/api/status
                                       ├── /api/status?backend=lilblue  → http://192.168.4.31:8792/api/status
                                       └── /api/status?backend=obd      → http://192.168.4.31:8791/api/status
```

Each forwarded request carries the user's BirdMug-Auth cookie/bearer
through, so the downstream `@require_auth` decorators keep working
unchanged. All four services share `BIRDMUG_JWT_SECRET` from Doppler
`birdmug-services/prd` — no extra auth wiring needed.

## One-time Toshi setup

```bash
# Create tunnel
cloudflared tunnel create ai-fleet
# Note the returned tunnel ID — paste it into the config below.

# Fix credentials permissions (cloudflared writes 400, needs 644)
chmod 644 ~/.cloudflared/<ai-fleet-tunnel-id>.json

# Write config — bridge networking so use container name, NOT localhost
cat > ~/.cloudflared/ai-fleet-config.yml << 'EOF'
tunnel: <ai-fleet-tunnel-id>
credentials-file: /etc/cloudflared/<ai-fleet-tunnel-id>.json

ingress:
  - hostname: ai.birdmug.com
    service: http://ai_fleet_dashboard:8794
  - service: http_status:404
EOF

# Register DNS
cloudflared tunnel route dns ai-fleet ai.birdmug.com
```

## Deploy / redeploy

```bash
cd ~/AIInfrastructure
git pull
flock -w 600 /tmp/toshi-deploy.lock \
  ~/toshi-infra/deploy/deploy.sh AI-Fleet-Dashboard main prod
```

deploy.sh handles the flock + Doppler injection automatically. Required
registration entries are already in `~/toshi-infra/deploy/deploy.sh`:

| Map | Value |
|---|---|
| `REPO_DIR_FOR_BRANCH` / `REPO_DIR` | `$HOME/AIInfrastructure` |
| `COMPOSE_SUBDIR` | `Birdmug-AI-Fleet-Dashboard` |
| `COMPOSE_FILE_MAP` | `docker-compose.prod.yml` |
| `DOPPLER_PROJECT` | `birdmug-services` |
| `HEALTH_ENDPOINTS` | `ai_fleet_dashboard:8794:/health` |

## Secrets (Doppler project: birdmug-services)

- `BIRDMUG_JWT_SECRET` — shared, already present (same as LilBlue/OBD/Reaper)
- `BUG_FAIRY_API_KEY` — shared, already present
- `BIRDMUG_AUTH_URL` — shared, already present
- `LILBLUE_URL` / `OBD_URL` / `REAPER_URL` — defaults to `http://192.168.4.31:879N`,
  override in Doppler only if the per-service ports ever change

## Port binding

The `ai_fleet_dashboard` container publishes its port to
`127.0.0.1:8794:8794` (NOT `0.0.0.0`). This dashboard has no LAN consumers —
only the cloudflared sidecar reaches it, and that's via the bridge network
DNS name `ai_fleet_dashboard:8794`. Tighter than LilBlue/Reaper's
`0.0.0.0:879N` because those expose proxy routes to LAN consumers like
Kyle-Rag; this one doesn't.

## Auth federation

The federation backend (`server/app.py::_forward_auth_headers`) copies the
incoming user's `birdmug_token` cookie, `bm_token` cookie, and/or
`Authorization` header onto the outbound request. Because
`accounts.birdmug.com` sets `birdmug_token` with `domain=.birdmug.com`,
every subdomain (including `ai.birdmug.com` and the downstream
`lilblue/obd/reaper.birdmug.com`) sees the same cookie automatically.

If you ever rotate `BIRDMUG_JWT_SECRET`, redeploy ALL FOUR services in
the same window (this one + LilBlue + OBD + Reaper) — otherwise the
federation backend will hold a different secret than the downstreams and
all forwarded requests will 401.

## Gunicorn worker model

```
gunicorn --bind 0.0.0.0:8794 \
  --worker-class gthread --workers 1 --threads 8 --timeout 60 \
  --graceful-timeout 30 server.app:app
```

Shorter timeout than LilBlue/Reaper (60s vs 660s) because this service
only forwards short status JSON polls — no long LLM streams pass through
it. If you ever federate the proxy routes (`/v1/*`, `/api/chat`, etc.)
through here too, bump the timeout to match LilBlue.

## Cloudflared healthcheck

Intentionally omitted — same rationale as LilBlue/Reaper. The cloudflared
binary self-monitors and reconnects; `restart: on-failure:3` handles
crashed binaries. The mount is now `:ro` so the tunnel can read its
credentials but can't write to the host filesystem.

## Network note

Uses **bridge networking** (`ai_fleet_net`). The cloudflared service
reaches the app via container DNS `http://ai_fleet_dashboard:8794`. To
reach the three downstream dashboards, the app uses Toshi's LAN IP
(`192.168.4.31:879N`) — that path works whether the downstream is
bridge-networked (LilBlue/Reaper) or host-networked (OBD), so we don't
need to be on the same docker network as any of them.

## Adding Uptime Kuma monitor

Per FRAMEWORKS.md, add a Kuma monitor against
`https://ai.birdmug.com/health` (no auth on `/health`, returns 200 with
`{"status":"ok"}`).

## Relationship to existing dashboards

The three per-service dashboards stay up and canonical. This service is
purely additive — kill it and the original URLs (lilblue/obd/reaper.birdmug.com)
still work. If you later decide to retire the per-service public URLs in
favor of `ai.birdmug.com/#reaper` etc., remove only their cloudflared
sidecars (the proxy containers stay since Kyle-Rag and ops-rag hit the
LAN ports, not the public hostnames).

See [`../falkensteink-API-Fleet-Dashboard.md`](../falkensteink-API-Fleet-Dashboard.md)
for the consumer-facing surface description (TBD — not strictly needed
since the dashboard is browser-only and BirdMug-Auth gates it).
