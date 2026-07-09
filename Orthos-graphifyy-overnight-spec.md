# Orthos — Graphifyy Overnight Run Spec

A spec for Codex (or whoever's wrenching on the Orthos / TabbyAPI side) to prep
Chris's 3090 for a one-night graphifyy run against Kyle's `falkensteink/`
monorepo. After the run, revert.

## Goal

For one overnight window, swap Orthos's loaded model from the current
`Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6` to an **instruct-tuned dense
model** (not coder-tuned), so Kyle can run `graphify extract` against a
~20-project source tree (mostly code, some markdown, no images, no PDFs) and
get high-quality semantic relationship extraction without paying Anthropic
tokens.

Coder-tuned is fine for code, but graphifyy's value-add is the cross-cutting
"why" — design rationale extracted from markdown, comments, READMEs, and the
relationships between code modules. That's prose-heavy reasoning where an
instruct model materially outperforms a coder model.

## Workload Profile (so you can size config correctly)

- **Protocol:** OpenAI-compatible chat-completions via the existing Orthos
  auth proxy at `http://100.114.166.24:8787/v1`. No new routes needed —
  graphifyy only hits `GET /v1/models` and `POST /v1/chat/completions`, both
  already allowed by the proxy allowlist.
- **Request volume:** roughly 200–600 sequential POSTs over 2–6 hours
  (one project at a time, hundreds of files). Single in-flight against
  TabbyAPI is fine — graphifyy's CLI is sequential, so the existing queue
  behavior on Orthos is correct.
- **Per-request shape:**
  - Input: 2k–10k tokens (a source file + extraction prompt)
  - Output: 200–1500 tokens (extracted nodes + relationships, JSON-ish)
  - No streaming required; non-streaming is fine.
  - No tool use, no function calling, no images.
- **Concurrency:** 1. Kyle's run is serial. No parallel requests from his side.
- **No embeddings against Orthos.** Those go to Kaydanski's `bge-m3` via the
  LilBlue proxy. Orthos doesn't need `/v1/embeddings` enabled.

## Requested Model

**Preferred:** `Qwen2.5-32B-Instruct` at exl3 4–6 bpw (whichever quant
matches your current exl3 workflow). Fits in 24 GB with room for 16k+
context.

**Acceptable fallbacks (any of these is fine if 32B is awkward to source):**
- `Qwen2.5-14B-Instruct` at exl3 4.0–6.0 bpw — ~8 GB, leaves headroom but is
  a quality step down vs 32B
- `Qwen2.5-Coder-32B-Instruct` — coder-tuned but the "instruct" finetune
  recovers most of the prose-reasoning gap; second-best choice if pure
  instruct isn't readily available
- Whatever 32B-class instruct model you already have a quant for and trust;
  the goal is "good general semantic extractor" not a specific weight set

**Avoid:** the current `Qwen3-Coder-30B-A3B` (already-loaded), `gemma-2-27b`
(weaker JSON adherence in my experience), `llama-3.1-8b` (too small).

## TabbyAPI Config Requirements

- **`max_seq_len`:** at least **16384**. Some of Kyle's larger Python
  modules + the extraction prompt will exceed 8k. 32768 if cache-mode-Q4 fits.
- **`cache_mode`:** Q4 or Q6 KV cache is fine — recovers VRAM at long
  context without quality loss on this workload.
- **Loaded model exposed in `/v1/models`:** the model name graphifyy sends
  must match what TabbyAPI advertises. Either:
  - Load the model with an alias matching what graphifyy sends, **or**
  - Tell Kyle the exact model id `/v1/models` returns so he can set
    `OPENAI_MODEL` to it.
- **Auth proxy + Tailscale Serve:** no changes — existing setup works.
- **Proxy allowlist:** no changes — `/v1/models` and `/v1/chat/completions`
  are already allowed.
- **Timeout:** existing `PROXY_TIMEOUT_SECONDS=3600` is plenty.

## Window

Kyle will start the run at a time you agree on (target: a night Chris isn't
gaming or running BG3 inference). Expected duration 2–6 hours; he'll
monitor the Blackflame dashboard at `127.0.0.1:8792` for Blocked / Degraded
states and stop if Chris needs the GPU back.

## Smoke Test (before Kyle kicks off the real run)

Kyle will run this against Orthos to confirm the model swap took:

```powershell
Invoke-RestMethod `
  -Uri 'http://100.114.166.24:8787/v1/models' `
  -Headers @{ Authorization = "Bearer $env:ORTHOS_BEARER_TOKEN" }
# expect: model id of the newly-loaded instruct model

Invoke-RestMethod `
  -Uri 'http://100.114.166.24:8787/v1/chat/completions' `
  -Method Post `
  -Headers @{
    Authorization  = "Bearer $env:ORTHOS_BEARER_TOKEN"
    'Content-Type' = 'application/json'
  } `
  -Body (@{
    model       = '<new-model-id>'
    messages    = @(@{ role = 'user'; content = 'In one sentence, what is dependency injection?' })
    max_tokens  = 80
    temperature = 0
  } | ConvertTo-Json -Depth 5)
# expect: coherent prose answer, ~50 tokens, no JSON, no code unless asked
```

If the answer comes back as a code snippet or starts with `def`, the wrong
model is still loaded.

## Rollback (after the run)

When Kyle says "done," reload `Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6`
so Chris's normal Roo / BG3 workflow is uninterrupted. No other state needs
to be touched.

## Open questions Codex / Chris should answer back

1. **Is there an existing context-length cap in TabbyAPI's running config
   that's lower than 16k?** If so, bump for this run.
2. **What's the exact `/v1/models` id of the swapped model?** Kyle needs it
   to set `OPENAI_MODEL` correctly.
3. **Any preferred swap window?** Kyle is flexible.
4. **Anything we should know about Tabby's hot-reload behavior?** If model
   swap requires a restart that drops in-flight Roo calls for Chris, we
   should sequence the swap when Chris is idle, not just when Kyle is ready.

## Why this matters (one paragraph for Chris)

Kyle's been evaluating a tool called `graphifyy` that builds a queryable
knowledge graph from a code+docs tree — replaces a lot of "grep around the
repo" time for Claude Code sessions. The default backend is Claude API
($$). Orthos is the obvious local alternative since the 3090 is the only
GPU in our combined fleet that can run a strong-enough model. One overnight
run gives Kyle a clean comparison: graph-quality vs Claude, at $0. If the
output is good, this becomes a recurring local-LLM workflow against
Orthos every few weeks when the falkensteink repo drifts enough to need a
re-index. If it's not, we learned cheap.
