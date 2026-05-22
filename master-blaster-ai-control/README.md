# Master Blaster AI Control

Manual pause/resume scripts for Master Blaster's local Ollama instance. Used to release the GPU before launching a game (especially BG3) and warm models back up after.

Master Blaster's role in the fleet: light-duty AI node — bge-m3 embeddings + qwen2.5:3b classifier. Service: `OllamaService`, listening on `127.0.0.1:11434` + `192.168.4.33:11434`.

## Files

| File | Purpose |
|---|---|
| `AI-Pause.ps1` | Queries `/api/ps`, unloads every loaded model via `keep_alive=0`, polls up to 15 s for eviction to complete, reports final state |
| `AI-Resume.ps1` | Sanity-checks Ollama, restarts the service if stopped, warms each model in `$CHAT_MODELS` + `$EMBED_MODELS` back into VRAM |
| `AI-Pause.cmd` / `AI-Resume.cmd` | Double-clickable launchers (handle `-ExecutionPolicy Bypass`) |
| `README.md` | This file |

Desktop shortcuts created at `%USERPROFILE%\Desktop\AI-Pause.lnk` and `AI-Resume.lnk` with hotkeys `Ctrl+Alt+P` (pause) and `Ctrl+Alt+R` (resume). Right-click → Properties → Shortcut key to change.

## Usage

**Before launching a game:** press `Ctrl+Alt+P`, watch for `GPU released for gaming.`

**After closing the game:** press `Ctrl+Alt+R`, watch for `Ready.`

Both windows auto-close after 3 seconds. Exit codes: 0 = success, 1 = API down / service issue, 2 = pause completed but at least one model failed to evict.

## Default warm set

Currently in `AI-Resume.ps1`:
- Chat: `qwen2.5:3b`  (~2.4 GB VRAM)
- Embed: `bge-m3:latest`  (~1.15 GB VRAM)

Total ~3.6 GB resident. Fits RX 580's 8 GB with room to spare.

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
