# LilBlue Dashboard — Toshi Deploy Notes

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

## Network note

LilBlue uses **bridge networking** (`lilblue_net`). The cloudflared service reaches the
app container via `http://lilblue_dashboard:8792` (container DNS name). Do NOT use
`localhost:8792` — that resolves to the cloudflared container's own loopback.

Contrast with OBD which uses `network_mode: host` (required for Tailscale), where
`localhost:8791` is correct.
