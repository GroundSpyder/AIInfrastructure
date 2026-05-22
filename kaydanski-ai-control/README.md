# Kaydanski AI Control

Scripts that live on Kaydanski itself to manage its local Ollama
instance. Source-of-truth here in the repo; deployed copies live at
`C:\Users\Kaiden\` on Kaydanski.

## Files

| File | Deployed at | Purpose |
|---|---|---|
| `ollama-warm.ps1` | `C:\Users\Kaiden\ollama-warm.ps1` | Warm the boot-time models into VRAM. Reads `ollama-warm-set.json` if present (set by the AI Fleet Dashboard GUI); otherwise uses hardcoded defaults (`qwen2.5:7b` chat + `bge-m3` embed). |

The existing `ollama-start.ps1` on Kaydanski (not in this repo - lives
only at `C:\Users\Kaiden\ollama-start.ps1`) starts the daemon at logon
via Task Scheduler. `ollama-warm.ps1` should be invoked **after**
`ollama-start.ps1`, either chained in the same scheduled task or as a
follow-on task with a 15 s delay.

## Why ollama-warm-set.json

The AI Fleet Dashboard (`Birdmug-AI-Fleet-Dashboard`) on Toshi has a
**warm-set editor** at `https://ai.birdmug.com/#models`. When Kyle
edits the warm-set in that UI, the dashboard writes
`C:\Users\Kaiden\ollama-warm-set.json` via SSH to Kaydanski.
`ollama-warm.ps1` reads that file at warm time so the GUI changes
take effect on the next boot or manual warm.

Schema:

```json
{
  "chat":  ["model1:tag", "model2:tag"],
  "embed": ["model3:tag"]
}
```

If the file is missing or invalid, `ollama-warm.ps1` falls back to its
hardcoded defaults and logs a warning. The fallback is deliberate -
losing the warm file should never prevent the box from booting warm.

## Scheduling

Right now `ollama-warm.ps1` is **not yet wired into a scheduled task**.
Manual run for testing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Kaiden\ollama-warm.ps1
```

To wire it into Kaydanski's logon flow, create a scheduled task that
runs at logon, with `ollama-start.ps1` as a dependency or 30 s delay
before this script fires. Once Ollama is responding, `ollama-warm.ps1`
takes ~10-20 s to warm both chat + embed models.

## Sister directory

`master-blaster-ai-control/` is the equivalent on Master Blaster -
slightly different shape (Pause / Resume / Bench scripts, since MB is
gaming-shared) but the warm-set integration is parallel.
