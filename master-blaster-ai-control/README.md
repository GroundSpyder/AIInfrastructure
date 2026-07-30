# Master Blaster AI Control

The **GPU gate**: Master Blaster is Kyle's gaming PC *and* a fleet AI node, and those two roles fight over a 16 GB card. This directory holds the automatic gate that stops Ollama while a game is running, plus the manual overrides.

Service: `OllamaService`, listening on `127.0.0.1:11434` + `192.168.4.33:11434`. Fleet role: `fleet/chat-quality` (qwen3:14b, MB-only) and half of `fleet/embed` (bge-m3, load-balanced with Kaydanski).

## Why the gate exists (2026-07-30)

Kyle deleted the entire Ollama model store on 2026-07-09 because "it kept kicking on and wrecking my PC while I was playing games." He was right, and the old scripts could not have prevented it:

1. **The fleet actively pulls this box into work.** The LiteLLM gateway load-balances `fleet/embed` across Kaydanski *and* Master Blaster with `simple-shuffle`, so every fleet embedding request is a coin flip that lands on the gaming GPU. `fleet/chat-quality` routes here exclusively and loads a ~9 GB model.
2. **`OLLAMA_KEEP_ALIVE=30m`** means one stray request pins that VRAM for half an hour.
3. **The old `AI-Pause.ps1` could not hold.** It unloaded models via `keep_alive=0` and left the service running. Its own header conceded "first request after pause will reload". The next coin-flip embed dragged the model straight back in, mid-game.
4. **The warm set does not fit alongside a game.** qwen3:14b + bge-m3 is ~11.5 GB of 16 GB. There is no polite coexistence at that size, so the gate is all-or-nothing.

Cost of getting this wrong, measured: reaper-dashboard filed **7,946 Bug Fairy reports** between 2026-07-09 and 2026-07-30 against a node that was intentionally unavailable.

## Design rule: fail-safe toward gaming

Every uncertain path favours the game, never the fleet. If the watchlist is unreadable, if a poll throws, or if the watcher process dies, **Ollama stays stopped**. The cost of that is a delayed reindex. The cost of the opposite is a stuttering game, which is the entire problem being solved.

## Files

| File | Purpose |
|---|---|
| `Game-Watch.ps1` | The watcher. Polls for game processes every 10 s; stops `OllamaService` when one appears, restarts and re-warms it after a grace period once none remain |
| `Install-GameWatch.ps1` | Registers the watcher as a SYSTEM scheduled task at boot. `-Uninstall`, `-Status` |
| `GpuGate.ps1` | Shared state helpers, dot-sourced by the other three. Owns the gate state file and the service start/stop primitives |
| `games.json` | Editable process watchlist. Re-read every poll, so no restart needed after an edit |
| `AI-Pause.ps1` | Manual override. **Stops the service** and records a `manual` pause that the watcher will not auto-release |
| `AI-Resume.ps1` | Starts the service, warms the models, releases the gate. Refuses while a watched game is running unless `-Force` |
| `AI-Pause.cmd` / `AI-Resume.cmd` | Double-clickable launchers. Route through `gsudo` because stopping a service needs elevation |
| `Verify-GPU.ps1` | Confirms inference is really on the GPU (see ollama#13920 silent CPU fallback) |

Runtime state lives in `%ProgramData%\falkensteink\` (`gpu-gate.json`, `gpu-gate.log`), **not** in this repo, because the watcher runs as SYSTEM while the hotkeys and the AI Fleet Dashboard run as Kyle.

## Usage

**Normal operation: do nothing.** Launch a game, the GPU is released within ~10 s. Close it, Ollama comes back ~60 s later and re-warms.

| Command | Purpose |
|---|---|
| `.\Game-Watch.ps1 -Status` | Current gate state, service state, API reachability |
| `.\Game-Watch.ps1 -Candidates` | Lists running processes over 300 MB and marks which are watched. Use this to find a game's process name |
| `Ctrl+Alt+P` | Manual pause. Outranks the watcher; holds until you resume |
| `Ctrl+Alt+R` | Manual resume |
| `.\Install-GameWatch.ps1 -Status` | Task state plus the last 20 gate-log lines |

**Adding a game:** run `-Candidates` while it is running, add the process name to the `processes` array in `games.json`. Trailing `*` is a prefix wildcard (`ShooterGame*`). No restart needed.

Exit codes - `AI-Pause`: 0 success, 1 stop failed, 2 stopped but port still answering. `AI-Resume`: 0 success, 1 warm failed, 4 refused because a game is running.

## Default warm set

Currently in `AI-Resume.ps1`:
- Chat: `qwen3:14b`  (~9 GB VRAM)
- Embed: `bge-m3:latest`  (~1.2 GB VRAM)

Total ~11.5 GB resident of the RX 9070 XT's 16 GB. This is deliberately too large to share with a game, which is why the gate is all-or-nothing rather than a smaller always-on footprint.

## Runtime override via warm-set.json

`AI-Resume.ps1` checks `$PSScriptRoot\warm-set.json` at startup. If
present, its `chat` and `embed` arrays override the hardcoded defaults.
If missing or invalid, the script falls back to defaults and logs a
warning (so a bad file never blocks the warm).

The AI Fleet Dashboard (`Birdmug-AI-Fleet-Dashboard` on Toshi) writes
this file via SSH when Kyle edits the warm-set in the GUI at
`https://ai.birdmug.com/#models`. See `server/models_api.py`
`WARM_SET_PATH['mb']`.

Schema:

```json
{
  "chat":  ["qwen3:14b"],
  "embed": ["bge-m3:latest"]
}
```

The file itself is `.gitignore`-d (it's user state, not source). Sister
script on Kaydanski: `kaydanski-ai-control/ollama-warm.ps1`.

## RX 9070 XT migration checklist

When the 9070 XT is installed. **Unlike Kaydanski (gfx1032, not on ROCm-Windows list), the 9070 XT IS officially supported by ROCm 7.2.1 on Windows.** Try ROCm first — when it works, it's ~45 tok/s vs Vulkan's lower ceiling. Fall back to Vulkan only if Ollama's open #13920 bug bites.

1. **Driver + Adrenalin**
   - Install AMD Adrenalin with full RDNA 4 / gfx1201 support
   - Reboot

2. **AMD HIP SDK 7.1.1 or newer** (this is what makes ROCm-with-Ollama actually work on 9070 XT — Ollama itself ships with too-old ROCm libraries)
   - Download from AMD's [ROCm Windows page](https://rocm.docs.amd.com/projects/install-on-windows/en/latest/reference/system-requirements.html)
   - Install to default path (`C:\Program Files\AMD\ROCm\7.1\`)
   - Confirms: `dir "C:\Program Files\AMD\ROCm\7.1\bin\rocblas\library"` should show `*gfx120*` files

3. **Point Ollama at the new ROCm libraries via NSSM**:
   ```
   nssm set OllamaService AppEnvironmentExtra ROCBLAS_TENSILE_LIBPATH=C:\Program Files\AMD\ROCm\7.1\bin\rocblas\library
   nssm restart OllamaService
   ```
   Pass each `KEY=VAL` as a **separate positional argument** if you add more env vars — space-joined string silently corrupts the env block (Kaydanski landmine, root [CLAUDE.md](../../CLAUDE.md) 2026-04-24 entry). Source recipe: [doroch.com](https://www.doroch.com/post/ai-on-amd-radeon-rx-9000-local-llm-ollama-rocm-gpt-oss-qwen3/).

4. **Verify GPU is actually doing the work** — this step matters more than usual because of [ollama#13920](https://github.com/ollama/ollama/issues/13920) (still open as of Jan 2026): Ollama detects the card but silently falls back to CPU with `"filtering device which didn't fully initialize"` in logs. CPU fallback = ~8-16 tok/s vs ~45 tok/s on GPU.
   ```
   curl http://localhost:11434/api/ps
   ```
   - `size_vram > 0` and ≈ `size` → ROCm working, GPU loaded
   - `size_vram` = 0 → fell back to CPU, check Ollama logs for "filtering device"
   - Run `AI-Resume.ps1` then a real `ollama run qwen2.5:7b "hi"` — should be >30 tok/s. If single-digit, you hit #13920.

5. **If ROCm fails to stabilize**, fall back to Vulkan (proven-working but lower peak perf):
   ```
   nssm set OllamaService AppEnvironmentExtra OLLAMA_VULKAN=1 OLLAMA_LLM_LIBRARY=vulkan
   nssm restart OllamaService
   ```
   Drop the `ROCBLAS_TENSILE_LIBPATH` var when doing this. Vulkan was Kaydanski's path because gfx1032 isn't on ROCm — for gfx1201 it's only a fallback.

6. **Bench before declaring done**:
   - Embedding: `bge-m3:latest`, target ~ 15+ embed/sec (Kaydanski hits 16.6 on a 6600)
   - Chat: `qwen2.5:7b`, target ~ 40+ tok/sec (Kaydanski hits 41 on Vulkan; 9070 XT on ROCm should match or beat)

7. **Step up the warm set** — 16 GB VRAM affords graduating to **qwen2.5:14b** (~9 GB). This makes MB a genuine fleet contributor for harder reasoning, not a duplicate of Kaydanski's 7b. Edit `AI-Resume.ps1` (uncomment the post-9070XT block already present):
   ```powershell
   $CHAT_MODELS  = @('qwen2.5:14b')
   $EMBED_MODELS = @()   # or keep @('bge-m3:latest') if MB should also serve embeds
   ```
   Both `qwen2.5:7b` and `qwen2.5:14b` were pre-pulled 2026-05-19. 7b stays available as a fast-response option.

   **VRAM math (16 GB):** 14b weights ~9 GB + KV cache for 8K context ~2-3 GB + driver/OS ~1-2 GB = 2-4 GB headroom. Tight but workable. Drop bge-m3 if context windows feel cramped.

8. **Update fleet strategy doc** — [c:/falkensteink/AI_FLEET_STRATEGY.md](../../AI_FLEET_STRATEGY.md) — Master Blaster's role bumps from "light classifier + embedder" to chat-capable (gaming-shared, hence the pause/resume scripts).

9. **Add Kuma monitors** — same pattern as Kaydanski, see [project_kuma_ai_fleet_monitors_2026-04-27.md](../../../Users/kylej/.claude/projects/c--falkensteink-ideaFairy/memory/project_kuma_ai_fleet_monitors_2026-04-27.md).

## Why manual, not auto-watch

Auto-detecting game launches via WMI process events is doable, but Kyle prefers explicit control — different games have different VRAM appetites, sometimes you want AI running alongside a low-load game, and the manual hotkey is fast enough. If preference flips later, add a `Start-MasterBlasterAIWatcher.ps1` that subscribes to `Win32_ProcessStartTrace` for a configured exe list and fires `AI-Pause.ps1`.

## Why `keep_alive=0`, not service stop

`keep_alive=0` evicts the model from VRAM but leaves the service responsive. If something genuinely needs to ping Ollama mid-game (an automation, a Kuma probe), it gets a slow first-response (model reloads) rather than a connection refused. Cleaner failure mode. If you want hard-stop later, set:

```powershell
Stop-Service -Name OllamaService
# ...
Start-Service -Name OllamaService
```

## No silent failures

Both scripts surface errors loudly per [root CLAUDE.md](../../CLAUDE.md) — no `try { ... } catch { }` swallows. `AI-Pause.ps1` exits 2 if a model is still loaded after the 15 s poll window, with the full `/api/generate` + `/api/embed` error strings. `AI-Resume.ps1` exits 1 if any model fails to warm.
