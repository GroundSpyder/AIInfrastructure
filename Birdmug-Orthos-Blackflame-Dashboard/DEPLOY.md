# OBD (Orthos Blackflame Dashboard) — Toshi Deploy Notes

## One-time Toshi setup (already done)

```bash
# Create tunnel
cloudflared tunnel create obd
# Returns tunnel ID: 2c5b1c79-bf31-4eaf-a2f0-23a64a65c74b

# Fix credentials permissions
chmod 644 ~/.cloudflared/2c5b1c79-bf31-4eaf-a2f0-23a64a65c74b.json

# Write config — host networking so localhost:8791 is correct
cat > ~/.cloudflared/obd-config.yml << 'EOF'
tunnel: 2c5b1c79-bf31-4eaf-a2f0-23a64a65c74b
credentials-file: /etc/cloudflared/2c5b1c79-bf31-4eaf-a2f0-23a64a65c74b.json

ingress:
  - hostname: obd.birdmug.com
    service: http://localhost:8791
  - service: http_status:404
EOF

# Register DNS
cloudflared tunnel route dns obd obd.birdmug.com
```

## Deploy / redeploy

```bash
cd ~/AIInfrastructure/Birdmug-Orthos-Blackflame-Dashboard
git pull
flock -w 600 /tmp/toshi-deploy.lock \
  doppler run --project birdmug-services --config prd -- \
  docker compose -f docker-compose.prod.yml up -d --build
```

## Secrets (Doppler project: birdmug-services)

- `BIRDMUG_JWT_SECRET` — shared, already present
- `BUG_FAIRY_API_KEY` — shared, already present
- `BIRDMUG_AUTH_URL` — shared, already present
- `ORTHOS_API_TOKEN` — **must be added** — bearer token for Chris's Orthos proxy
- `ORTHOS_BASE_URL` — defaults to `https://chris13600k.tail406192.ts.net/v1`
- `ORTHOS_TEST_MODEL` — defaults to `Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6`

## Network note

OBD uses `network_mode: host` because it must reach `chris13600k` via Tailscale.
Tailscale policy routing (table 52) is only visible from the host network namespace —
Docker bridge networks cannot route to Tailscale peers.

Once `ORTHOS_API_TOKEN` is in Doppler, redeploy to activate:
```bash
doppler secrets set ORTHOS_API_TOKEN=<token> --project birdmug-services --config prd
cd ~/AIInfrastructure/Birdmug-Orthos-Blackflame-Dashboard
flock -w 600 /tmp/toshi-deploy.lock \
  doppler run --project birdmug-services --config prd -- \
  docker compose -f docker-compose.prod.yml up -d
```
