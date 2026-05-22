# orthos-comm n8n workflows

Two workflows on Toshi's n8n that turn the `orthos` channel into an
event-driven inbox: when chris-bot posts directed asks or status FYIs,
notify Kyle without making him scan the channel manually.

| Workflow | ID | Schedule | Purpose |
|---|---|---|---|
| `botchat-urgent-relay` | `bcr01` | Every 5 minutes | New chris-bot posts containing `@kyle-bot` → DM kyle-bot to keilai |
| `botchat-daily-digest` | `bcd01` | Daily 09:00 CT | Summarize the last 24 h of chris-bot FYI posts (no `@kyle-bot`) via qwen2.5:7b on Kaydanski → DM kyle-bot to keilai |

Both DM into the existing kyle-bot ↔ keilai direct channel
(`cqhn533i8tnszryak11ysnkj3r`). Kyle handles asks via `/botchat` in any
Claude Code session.

## Architecture

```
botchat-urgent-relay (every 5 min)
────────────────────────────────────
Schedule → Compute Cursor → Mattermost GET posts → Filter chris-bot @ kyle-bot → DM each via Mattermost POST

botchat-daily-digest (daily 09:00)
────────────────────────────────────
Schedule → 24h window → Mattermost GET posts → Filter chris-bot non-mention → Build digest prompt → Ollama qwen2.5:7b → Format → DM
```

The two workflows have **independent state**. Urgent-relay tracks a
cursor in n8n's workflow-static-data; digest re-queries the full 24 h on
each run. Some overlap between the urgent and digest signals is fine —
urgent-relay alerts on `@kyle-bot` mentions, digest covers the FYI
remainder.

## Env vars consumed

Both workflows read `$env.MATTERMOST_KYLE_BOT_TOKEN` from the n8n
container's environment. That env var is set via Doppler
`birdmug-infra / prd_n8n` and injected by `~/n8n/redeploy.sh`. The
secret value matches what's in `birdmug-services / prd_orthos_comm`
(the orthos-comm CLI's canonical config) — same kyle-bot token in two
Doppler configs because n8n + the per-host CLI are separate consumers.

If you rotate the kyle-bot token, update **both** Doppler configs and
redeploy n8n.

## Channel + bot IDs (hardcoded in the workflow JSON)

- Channel `orthos`: `qoia7dfowb8q9n16ukkidb874c`
- chris-bot user id: `b5jiw3sk13rbibcbt4t98gf1ra`
- kyle-bot ↔ keilai DM channel: `cqhn533i8tnszryak11ysnkj3r`
- Mattermost base URL: `https://chat.birdmug.com/api/v4`

## Ollama config (digest only)

- Endpoint: `http://100.83.51.117:11434/api/generate` (Kaydanski via Tailscale)
- Model: `qwen2.5:7b`
- continueOnFail: true (digest falls back to static template if Kaydanski is unreachable)

## Operational

**Re-import after editing the JSON locally:**

```bash
# from MB:
scp c:/falkensteink/AIInfrastructure/orthos-comm/n8n/botchat-urgent-relay.json \
    falkensteink@192.168.4.31:/tmp/
ssh falkensteink@192.168.4.31 "docker cp /tmp/botchat-urgent-relay.json n8n:/tmp/ && \
                                docker exec n8n n8n import:workflow --input=/tmp/botchat-urgent-relay.json"
# n8n CLI deactivates on import; flip active back on:
ssh falkensteink@192.168.4.31 'sudo docker exec n8n_postgres psql -U n8n -d n8n -c "UPDATE workflow_entity SET active = true WHERE id = '"'"'bcr01'"'"';"'
ssh falkensteink@192.168.4.31 "docker restart n8n"
```

**One-shot activate via SQL is safe.** Repeated SQL patches against the
same workflow develop runtime corruption per `feedback_n8n_workflow_corruption_via_sql_patches.md` —
import + a single activate UPDATE is well within the safe pattern.
If a workflow ever needs more than that (e.g. patching node bodies),
use delete + re-import, not iterative UPDATEs.

**Check execution history:**

```sql
SELECT "workflowId", status, "startedAt", "stoppedAt"
FROM execution_entity
WHERE "workflowId" IN ('bcr01','bcd01')
ORDER BY "startedAt" DESC LIMIT 20;
```

**Pause a workflow temporarily:** flip `active=false` in `workflow_entity`
and restart n8n. (Or use the n8n web UI at https://n8n.birdmug.com.)

## Smoke test

Post a test message from chris-bot mentioning `@kyle-bot`:

```bash
ssh falkensteink@192.168.4.31 \
  "T=<chris-bot-token>; curl -s -X POST -H \"Authorization: Bearer \$T\" \
   -H 'Content-Type: application/json' \
   -d '{\"channel_id\":\"qoia7dfowb8q9n16ukkidb874c\",\"message\":\"@kyle-bot smoke test\"}' \
   http://localhost:8065/api/v4/posts"
```

Wait 5 minutes (next bcr01 tick), then check the kyle-bot DM channel
for a relay message. Delete the smoke-test post afterwards.

## Failure modes worth knowing

| Symptom | Cause | Fix |
|---|---|---|
| No DM despite a chris-bot `@kyle-bot` post | bcr01 inactive or n8n down | Check `SELECT active FROM workflow_entity WHERE id='bcr01'` + `docker ps mattermost n8n` |
| Mattermost 401 in execution logs | kyle-bot token rotated / env var stale | Update Doppler `birdmug-infra/prd_n8n`, run `~/n8n/redeploy.sh` |
| Daily digest says "Ollama unreachable" | Kaydanski Ollama down or Tailscale issue | Check `curl http://100.83.51.117:11434/api/version` from Toshi |
| Workflow fires but no posts pass filter | chris-bot didn't actually post in window, or the @kyle-bot string isn't literal | Check Mattermost UI; the filter is a literal `.includes('@kyle-bot')` — variants like `@kylebot` won't match |
| Cursor stuck (urgent-relay keeps seeing same post) | static data write failed mid-run | n8n web UI → workflow → ⋯ menu → "Settings" → "Reset workflow data" |
