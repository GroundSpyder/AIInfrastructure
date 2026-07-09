# LilBlue Dashboard — Toshi Deploy Notes

LilBlue is both a dashboard *and* an Ollama proxy. The dashboard at
`https://lilblue.birdmug.com/` (BirdMug-Auth protected) shows live traffic,
model status, and recent generation metrics. The proxy routes — `/v1/*` and
`/api/*` — forward unauthenticated to Ollama on Kaydanski and are reachable
from the LAN at `http://192.168.4.31:8792`. Tracker metrics from the proxy
populate the dashboard's traffic table.

## One-time Toshi setup (already done)

```bash
# Create tunnel
cloudflared tunnel create lilblue
# Returns tunnel ID: df4f7739-a21f-49e9-b10c-033f498e078c

# Fix credentials permissions (cloudflared writes 400, needs 644)
chmod 644 ~/.cloudflared/df4f7739-a21f-49e9-b10c-033f498e078c.json

# Write config — note: bridge networking so use container name, NOT localhost
cat > ~/.cloudflared/lilblue-config.yml << 'EOF'
tunnel: df4f7739-a21f-49e9-b10c-033f498e078c
credentials-file: /etc/cloudflared/df4f7739-a21f-49e9-b10c-033f498e078c.json

ingress:
  - hostname: lilblue.birdmug.com
    service: http://lilblue_dashboard:8792
  - service: http_status:404
EOF

# Register DNS
cloudflared tunnel route dns lilblue lilblue.birdmug.com
```

## Deploy / redeploy

```bash
cd ~/AIInfrastructure/Birdmug-LilBlue-Dashboard
git pull
flock -w 600 /tmp/toshi-deploy.lock \
  doppler run --project birdmug-services --config prd -- \
  docker compose -f docker-compose.prod.yml up -d --build
```

## Secrets (Doppler project: birdmug-services)

- `BIRDMUG_JWT_SECRET` — shared, already present
- `BUG_FAIRY_API_KEY` — shared, already present
- `BIRDMUG_AUTH_URL` — shared, already present
- `OLLAMA_URL` — defaults to `http://kaydanskipc:11434`, override in Doppler if needed
- `LILBLUE_TEST_MODEL` — defaults to `qwen2.5:7b`

## Port binding and LAN exposure

The `lilblue-dashboard` container publishes its port to `0.0.0.0:8792:8792`
(not `127.0.0.1`). This is intentional so LAN clients — primarily Kyle-Rag
running on Kaydanski's Docker Desktop — can reach the proxy at
`http://192.168.4.31:8792`. UFW is inactive on Toshi, so the LAN-binding
alone makes the port reachable from any host on the local network.

The dashboard root (`/`) and the `/api/status` + `/api/test` endpoints stay
behind BirdMug-Auth. The proxy routes (`/v1/*`, `/api/generate`,
`/api/chat`, `/api/embed`, `/api/embeddings`, `/v1/models`) are intentionally
**unauthenticated** — clients like Kyle-Rag, ops-rag-server, and n8n
workflows don't pass JWTs. The tailnet/LAN boundary is the access control,
not bearer tokens.

If a future requirement adds a public-internet path to the proxy routes,
add auth at that layer (cloudflared service token, reverse proxy bearer
check) — do NOT rely on the dashboard's `@require_auth` since the proxy
endpoints deliberately don't use it.

## Gunicorn worker model

The Dockerfile.prod CMD pins:

```
gunicorn --bind 0.0.0.0:8792 \
  --worker-class gthread --workers 1 --threads 8 --timeout 360 \
  server.app:app
```

**Why gthread, not the default sync worker:** Kyle-Rag fires concurrent
`/api/embed` requests during ingest. With the previous `--workers 2` sync
model, two embed requests would block all other traffic (chat probes,
health checks, dashboard pollers) for the full inference window — we saw
30 s timeouts on the dashboard during ingest bursts. gthread keeps one
process (so the in-memory `MetricsTracker` singleton in `server/tracker.py`
stays shared across all requests) and serves up to 8 concurrent requests
on threads. Long timeout (360 s) tolerates slow Ollama embed batches on
busy reindex runs.

If you bump `--threads`, also bump `memory:` in `docker-compose.prod.yml`
(currently 256 M — was 128 M before the gthread move). Each thread holds
a small request buffer plus whatever the response streaming carries.

## Cloudflared healthcheck

The cloudflared service uses `curl -sf http://localhost:2000/healthz`,
not `wget`. The `cloudflare/cloudflared:2026.3.0` image ships with `curl`
but **no `wget` binary** — the previous `wget -qO-` check exited 127 and
made the container show as unhealthy even though the tunnel was up. If
you switch base images, re-check what's installed; the cloudflared image
is intentionally minimal.

## Network note

LilBlue uses **bridge networking** (`lilblue_net`). The cloudflared service reaches the
app container via `http://lilblue_dashboard:8792` (container DNS name). Do NOT use
`localhost:8792` — that resolves to the cloudflared container's own loopback.

Contrast with OBD which uses `network_mode: host` (required for Tailscale), where
`localhost:8791` is correct.
