# LilBlue API

LilBlue is Kyle's shared local AI inference node running on Kaydanski (Kaiden's gaming PC on the home tailnet).
It exposes Ollama's full model catalog — embeddings, chat, and completions — with no authentication required (tailnet is the boundary).

## Owner

LilBlue is Kyle's service running on Kaydanski. Kaiden owns the hardware; LilBlue is a polite boarder.
Do not assume exclusive use — Kaiden games on this machine. See gaming-courtesy rules below.

## Current Endpoints

Primary (tailnet hostname):

```text
http://kaydanskipc:11434
```

Direct Tailscale IP (if DNS resolution fails):

```text
http://100.83.51.117:11434
```

Use the hostname first. Fall back to the IP if you're seeing DNS failures.

## Authentication

None. Tailnet membership is the only access control.
LilBlue is **not** reachable from the public internet — Windows Firewall blocks non-tailnet traffic.

## Models

| Model | Purpose | VRAM | Speed |
|---|---|---|---|
| `bge-m3` | Embeddings (Kyle-Rag + corpus ingestion) | ~1.2 GB | ~16 embeds/sec (Vulkan GPU) |
| `qwen2.5:7b` | Fast chat, intent classification, tagging | ~5 GB | ~30 tok/sec (Vulkan GPU) |
| `qwen3:30b-a3b` | High-quality chat (MoE, CPU-only — too large for 8 GB VRAM) | 18.5 GB RAM | slower, CPU |

GPU: AMD RX 6600 (RDNA2, 8 GB VRAM). Vulkan backend active via `OLLAMA_VULKAN=1` + `OLLAMA_LLM_LIBRARY=vulkan`.

## Supported Routes

### Ollama-native

```text
POST /api/chat         — chat completion
POST /api/embed        — embeddings
POST /api/generate     — raw completion
GET  /api/ps           — loaded models + VRAM usage
GET  /api/tags         — model catalog
```

### OpenAI-compatible

```text
POST /v1/chat/completions
POST /v1/embeddings
```

Pass any non-empty string as the API key — Ollama ignores it:

```text
Authorization: Bearer ollama
```

## Environment Config

For Ollama-native clients:

```text
OLLAMA_URL=http://kaydanskipc:11434
```

For OpenAI-compatible clients:

```text
OPENAI_BASE_URL=http://kaydanskipc:11434/v1
OPENAI_API_KEY=ollama
```

## Recommended `keep_alive`

**This matters.** Loaded models sit in Kaiden's gaming GPU VRAM.

| Use case | `keep_alive` | Reason |
|---|---|---|
| Chat / one-off query | `0s` | qwen2.5:7b is 5 GB. Release VRAM immediately — don't hold the GPU between calls. |
| Bulk embeddings (backfill, reindex) | `5m`–`30m` | Avoid reload penalty between bursts. bge-m3 (1.2 GB) is small enough to leave warm. |

## Example Requests

List loaded models:

```bash
curl http://kaydanskipc:11434/api/ps
```

Chat completion (Ollama-native):

```bash
curl -s http://kaydanskipc:11434/api/chat \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Reply exactly: LilBlue ready"}],
    "stream": false,
    "keep_alive": "0s"
  }'
```

Embeddings:

```bash
curl -s http://kaydanskipc:11434/api/embed \
  -d '{"model": "bge-m3", "input": ["hello world"]}'
```

Chat completion (OpenAI-compatible):

```bash
curl -s http://kaydanskipc:11434/v1/chat/completions \
  -H "Authorization: Bearer ollama" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Reply exactly: LilBlue ready"}],
    "max_tokens": 10
  }'
```

## Service Shape

| | |
|---|---|
| **Process** | `ollama.exe serve` |
| **NSSM service** | `OllamaService` — AUTO_START, LocalSystem, restart-on-exit (2s delay) |
| **Port** | `11434` (TCP) bound to `0.0.0.0` |
| **Priority** | BelowNormal — yields to games |
| **Max loaded models** | 1 at a time (`OLLAMA_MAX_LOADED_MODELS=1`) |
| **Keep-alive default** | 30m (overridden per-call — see table above) |
| **Logs** | `C:\Users\Kaiden\ollama-logs\service-stdout.log` / `service-stderr.log` (10 MB rotation) |

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

## Gaming Courtesy

Kaiden plays games on this machine. LilBlue is a polite boarder.

- Ollama runs at **BelowNormal** CPU priority.
- Any loaded chat model sits in Kaiden's gaming GPU VRAM. `keep_alive=0s` on every chat call is **mandatory** — not optional.
- `AI-Pause.cmd` on Kaiden's desktop hard-stops Ollama and fully releases the GPU. If LilBlue goes unreachable around gaming hours, he may have paused it — this is expected and fine.
- If Kaydanski is unreachable, callers should fall back gracefully. Do not retry-loop into Kaydanski from a tight loop.

## Topology

```text
Kyle's services (Toshi / local)
  -> http://kaydanskipc:11434        (tailnet)
  -> OllamaService (NSSM)
  -> ollama.exe serve
  -> AMD RX 6600 (Vulkan) / CPU fallback for oversized models
```

Kyle-Rag (public-facing RAG):

```text
https://ik.birdmug.com
  -> cloudflared tunnel on Toshi
  -> kaydanskipc:8030 (Kyle-Rag personal IK, Docker)
  -> kaydanskipc:11434 (LilBlue embeddings)
```

Ollama is NOT directly public-facing. Everything that needs public inference goes through an authenticated layer (Kyle-Rag, or a project's own API).

## Troubleshooting

| Symptom | First check |
|---|---|
| Connection refused on 11434 | Is `OllamaService` running? `sc query OllamaService`. Did Kaiden pause it? `AI-Pause.cmd` stops it. |
| Inference painfully slow | Check `GET /api/ps` — is Vulkan active? Service-stdout.log should show `ggml_vulkan: Found 1 Vulkan devices` on startup. If missing, `OLLAMA_VULKAN=1` may have been dropped from NSSM env. |
| bge-m3 embedding times out | Concurrent chat model is loaded and VRAM is saturated. Wait for the chat call to finish (and its keep_alive to expire), then retry. |
| `docker pull` / `git push` fails over SSH | WCM gotcha — see KAYDANSKI.md "Windows Credential Manager gotcha." Has nothing to do with Ollama. |
| Machine unreachable overnight | Sleep timeout re-set by Windows update. Run: `powercfg /change standby-timeout-ac 0` on Kaydanski. |

## Security Notes

`kaydanskipc` and `100.83.51.117` are tailnet addresses — not reachable from the public internet.

Ollama has **no bearer token**. The access boundary is tailnet membership. Do not expose port 11434 through a public tunnel without adding an authenticated proxy in front of it first.
