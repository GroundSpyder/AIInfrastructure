# AI Fleet Dashboard — Toshi Deploy Notes

The AI Fleet Dashboard is the unified entry point for fleet model
visibility + control. Four tabs:

```
   browser  ─►  ai.birdmug.com
                  │
                  ├── tab REAPER   ──► iframe → https://reaper.birdmug.com/    (original CSS, full chrome)
                  ├── tab LILBLUE  ──► iframe → https://lilblue.birdmug.com/   (original CSS, full chrome)
                  ├── tab OBD      ──► iframe → https://obd.birdmug.com/       (original CSS, full chrome)
                  └── tab MODELS   ──► iframe → /models    (served by THIS container — fleet model CRUD)
```

The three per-service tabs are pure iframes carrying the user's
`birdmug_token` cookie (domain `.birdmug.com`) — no federation, no
copied CSS, no drift. Kyle's 2026-05-21 directive: each tab must look
like its original page. We dropped `?embed=1` so the inner headers
render normally.

The MODELS tab is served by this container at `/models`. It talks to:

```
   ai_fleet_dashboard container
       │
       ├── HTTP  ──► http://192.168.4.33:11434     (MB Ollama — read /api/ps, /api/tags, /api/show; write /api/generate, /api/pull, /api/delete)
       ├── HTTP  ──► http://kaydanskipc:11434      (Kaydanski Ollama — same)
       ├── SSH   ──► Kyle@192.168.4.33             (MB control plane — nssm get/set, restart, warm-set.json)
       └── SSH   ──► Kaiden@kaydanskipc            (Kaydanski control plane — same)
```

**Why SSH instead of a per-host Flask agent.** Kyle's rule (see
`memory/feedback_ssh_over_windows_agents.md`): "the little agents keep
dying silently and I have to reboot them. SSH just works." OpenSSH on
Windows is a first-class Microsoft service, restart-resilient.

## One-time Toshi setup

```bash
# Tunnel + DNS
cloudflared tunnel create ai-fleet
chmod 644 ~/.cloudflared/<ai-fleet-tunnel-id>.json

cat > ~/.cloudflared/ai-fleet-config.yml << 'EOF'
tunnel: <ai-fleet-tunnel-id>
credentials-file: /etc/cloudflared/<ai-fleet-tunnel-id>.json

ingress:
  - hostname: ai.birdmug.com
    service: http://ai_fleet_dashboard:8794
  - service: http_status:404
EOF

cloudflared tunnel route dns ai-fleet ai.birdmug.com
```

## One-time SSH key authorization on MB + Kaydanski

The dashboard container uses Toshi's host SSH key
(`/home/falkensteink/.ssh/id_ed25519`) to reach the two Windows hosts.
The corresponding public key must be installed in
`C:\ProgramData\ssh\administrators_authorized_keys` on each (since
both users — `Kyle` on MB, `Kaiden` on Kaydanski — are Administrators,
Windows OpenSSH uses the admin-scope authorized_keys file, not the
per-user `~/.ssh/authorized_keys`).

**Format** — keep the `from=` clause for safety, matching Toshi's
tailnet + LAN IPs:

```
from="100.107.130.46,192.168.4.31" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5...toshi-falkensteink-fleet-dashboard
```

**Master Blaster** — current key (toshi-falkensteink-fleet-dashboard)
was installed 2026-05-21. To re-install or refresh:

```powershell
# On MB, as Kyle (admin). gsudo is installed so no UAC click needed.
gsudo powershell -NoProfile -Command "notepad C:\ProgramData\ssh\administrators_authorized_keys"
# Paste the public key line ending with toshi-falkensteink-fleet-dashboard
```

**Kaydanski** — equivalent: `gsudo powershell -NoProfile -Command
"notepad C:\ProgramData\ssh\administrators_authorized_keys"` as Kaiden.

**Verify from Toshi** (run on Toshi itself):

```bash
ssh -o BatchMode=yes Kyle@192.168.4.33 "hostname && nssm version"
ssh -o BatchMode=yes Kaiden@kaydanskipc  "hostname && nssm version"
```

Both must return host + nssm version without prompting.

## Deploy / redeploy

```bash
cd ~/AIInfrastructure
git pull
flock -w 600 /tmp/toshi-deploy.lock \
  ~/toshi-infra/deploy/deploy.sh AI-Fleet-Dashboard main prod
```

`deploy.sh` handles the flock + Doppler injection. Registration entries
required in `~/toshi-infra/deploy/deploy.sh`:

| Map | Value |
|---|---|
| `REPO_DIR_FOR_BRANCH` / `REPO_DIR` | `$HOME/AIInfrastructure` |
| `COMPOSE_SUBDIR` | `Birdmug-AI-Fleet-Dashboard` |
| `COMPOSE_FILE_MAP` | `docker-compose.prod.yml` |
| `DOPPLER_PROJECT` | `birdmug-services` |
| `HEALTH_ENDPOINTS` | `ai_fleet_dashboard:8794:/health` |

## Secrets (Doppler project: birdmug-services)

- `BIRDMUG_JWT_SECRET` — shared with LilBlue/Reaper/OBD. Used for
  `@require_auth` on `/`, `/models`, and every `/api/models/*` route.
- `BUG_FAIRY_API_KEY` — shared.
- `BIRDMUG_AUTH_URL` — shared, defaults to `https://accounts.birdmug.com`.
- `FLEET_AUDIT_PATH` — defaulted to `/data/fleet_audit.log`; override
  only if mount point changes.

## Volume mounts

| Host path | Container path | Mode | Purpose |
|---|---|---|---|
| `/home/falkensteink/.ssh/id_ed25519` | `/root/.ssh/id_ed25519` | ro | SSH key for MB + Kaydanski control |
| `/home/falkensteink/.ssh/known_hosts` | `/root/.ssh/known_hosts` | ro | Avoid first-use prompt; allow strict checking once cached |
| named volume `ai_fleet_audit_data` | `/data` | rw | Audit log (`fleet_audit.log`) — survives rebuilds |

## Port binding

`127.0.0.1:8794:8794` (localhost-only). The cloudflared sidecar
reaches the app via bridge-network DNS `ai_fleet_dashboard:8794`. No
LAN consumers — every external reach is through the tunnel.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET    | `/`                                        | yes | Outer tab shell |
| GET    | `/models`                                  | yes | Models management page |
| GET    | `/fleet.png`                               | no  | Favicon |
| GET    | `/health`                                  | no  | Watchdog + Kuma probe |
| GET    | `/api/models/hosts`                        | yes | Host registry |
| GET    | `/api/models/<host>/ps`                    | yes | Loaded models (Ollama `/api/ps`) |
| GET    | `/api/models/<host>/tags`                  | yes | Installed models (Ollama `/api/tags`) |
| POST   | `/api/models/<host>/show`                  | yes | Model details |
| POST   | `/api/models/<host>/load`                  | yes | Warm into VRAM (`{model, strict_gpu, keep_alive}`) |
| POST   | `/api/models/<host>/unload`                | yes | Evict (`{model}`, sets `keep_alive=0s`) |
| POST   | `/api/models/<host>/pull`                  | yes | Pull new — streams SSE progress |
| DELETE | `/api/models/<host>/delete`                | yes | Delete — requires `{model, confirm_name: <same>}` |
| GET    | `/api/models/<host>/env`                   | yes | NSSM AppEnvironmentExtra (via SSH) |
| PUT    | `/api/models/<host>/env`                   | yes | Replace NSSM env (via SSH) — caller must restart |
| POST   | `/api/models/<host>/restart-ollama`        | yes | `nssm restart OllamaService` (via SSH) |
| GET    | `/api/models/<host>/warm-set`              | yes | Read warm-set.json (via SSH) |
| PUT    | `/api/models/<host>/warm-set`              | yes | Write warm-set.json (via SSH) |
| GET    | `/api/audit`                               | yes | Last 200 audit entries |

`<host>` is `mb` or `kaydanski`.

## Gunicorn worker model

```
gunicorn --bind 0.0.0.0:8794 \
  --worker-class gthread --workers 1 --threads 8 --timeout 120 \
  --graceful-timeout 30 server.app:app
```

Timeout bumped to 120s (was 60s) to cover `nssm restart` and
`/api/show` round-trips that include an SSH leg. SSE pull-progress is
exempt from this timeout because gthread streams responses without
counting reader idle time as inactivity.

## Cloudflared healthcheck

Intentionally omitted — same rationale as LilBlue/Reaper. The
cloudflared binary self-monitors; `restart: on-failure:3` handles
crashes. Mount is `:ro`.

## Kuma monitoring

Required per FRAMEWORKS.md: Kuma external HTTP probe against
`https://ai.birdmug.com/health` (no auth on `/health`, returns 200 with
`{"status":"ok"}`).

## Audit log

Every write op (load, unload, pull, delete, env_set, restart, warm-set
write) appends one JSON line to `/data/fleet_audit.log`. Tail via
`GET /api/audit` (returns the most recent 200 entries newest-last).

## Relationship to existing dashboards

The three per-service dashboards (LilBlue, Reaper, OBD) remain canonical
and reachable at their own URLs. This service is purely additive:
- killing this container does NOT take down lilblue/reaper/obd
- killing this container DOES disable the unified MODELS view + the
  cross-host model CRUD GUI (you can still drive Ollama directly per
  host via SSH or LAN HTTP).
