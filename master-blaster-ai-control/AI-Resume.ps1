# AI-Resume.ps1 - bring Master Blaster's Ollama back and warm the default models.
# Run after closing a game; mirrors what Ollama would do lazily on first request,
# but front-loads the slow load so the next real call is fast.
#
# 2026-07-30: now gate-aware. AI-Pause stops the service outright rather than
# unloading models, so resuming has to start it again before warming. Refuses to
# resume while a watched game is still running unless -Force is passed, because
# Game-Watch.ps1 would only pause it again seconds later and the flapping would
# cost a model load each time.
#
#   -Force   resume even if the gate is held by a running game (the watcher
#            passes this when IT is the one releasing the gate)

[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'GpuGate.ps1')
$OLLAMA = 'http://localhost:11434'

if (-not (Enter-GateLock)) {
    Write-Host '[AI-Resume] Could not take the gate lock (another gate operation is in progress). Try again.' -ForegroundColor Red
    exit 1
}

try {

# Ask whether a game is ACTUALLY running rather than trusting the gate's owner
# field. The previous version refused only when owner was 'game', so the common
# real-world sequence - pause by hand, play, then hit Ctrl+Alt+R out of habit -
# sailed straight through and warmed ~11 GB into VRAM mid-session.
$runningGame = Get-RunningGame
if ($runningGame -ne '' -and -not $Force) {
    if ($runningGame -eq '?unknown') {
        Write-Host '[AI-Resume] Cannot determine whether a game is running (watchlist unreadable).' -ForegroundColor Yellow
        Write-Host '[AI-Resume] Refusing to resume. Re-run with -Force to override.' -ForegroundColor Yellow
        Write-GateLog 'manual resume refused, game state unknown'
    } else {
        Write-Host "[AI-Resume] '$runningGame' is running - resuming would take the GPU back mid-game." -ForegroundColor Yellow
        Write-Host '[AI-Resume] Close the game, or re-run with -Force to override.' -ForegroundColor Yellow
        Write-GateLog "manual resume refused, '$runningGame' still running"
    }
    exit 4
}

# The service is stopped whenever the gate is engaged, so start it before we try
# to talk to the API. Start-OllamaHard logs its own failures.
$svcNow = Get-OllamaService
if ($null -eq $svcNow) {
    Write-Host '[AI-Resume] OllamaService is not installed on this machine.' -ForegroundColor Red
    Write-GateLog 'resume failed: OllamaService not installed' 'ERROR'
    exit 1
}
if ($svcNow.Status -ne 'Running') {
    Write-Host '[AI-Resume] OllamaService is stopped, starting it ...' -ForegroundColor Cyan
    if (-not (Start-OllamaHard)) {
        Write-Host '[AI-Resume] FAILED to start OllamaService. Try running as administrator.' -ForegroundColor Red
        exit 1
    }
    # Ollama needs a moment after the service reports Running before it binds.
    Start-Sleep -Seconds 3
}

# Default warm set for Master Blaster (RX 9070 XT / 16 GB VRAM / Vulkan).
# Picked 2026-05-19 after benching qwen2.5:14b (33 t/s), qwen3:14b (44 t/s),
# phi4:14b (51 t/s). qwen3:14b chosen for fleet-family consistency (drop-in
# template compat with the rest of the qwen2.5 surface) over Phi-4's speed
# edge. VRAM footprint: qwen3 ~10 GB + bge-m3 ~1.2 GB = ~11 GB / 16 GB,
# leaving ~5 GB for KV cache + driver overhead.
#
# Caveat: qwen3 has dual "thinking" / "non-thinking" modes. For everyday
# chat use, consumers should prefix prompts with `/no_think` (qwen3 family
# respects this) to suppress chain-of-thought generation that would
# otherwise slow short-prompt latency. Warm-up here doesn't trigger it.
$CHAT_MODELS  = @('qwen3:14b')
$EMBED_MODELS = @('bge-m3:latest')

# Prior warm set (RX 580 era):
# $CHAT_MODELS  = @('qwen2.5:3b')
# $EMBED_MODELS = @('bge-m3:latest')

# Override defaults from warm-set.json if it exists. The AI Fleet
# Dashboard writes this file via SSH when Kyle edits the warm-set in
# the GUI - see Birdmug-AI-Fleet-Dashboard/server/models_api.py.
# Falls through to the hardcoded defaults above when missing or invalid
# so a corrupt JSON file never prevents the box from booting warm.
$warmSetPath = Join-Path $PSScriptRoot 'warm-set.json'
if (Test-Path -LiteralPath $warmSetPath) {
    try {
        $warmSet = Get-Content -Raw -LiteralPath $warmSetPath | ConvertFrom-Json
        if ($warmSet.chat -is [array] -and $warmSet.chat.Count -ge 0) {
            $CHAT_MODELS = @($warmSet.chat)
        }
        if ($warmSet.embed -is [array] -and $warmSet.embed.Count -ge 0) {
            $EMBED_MODELS = @($warmSet.embed)
        }
        Write-Host "[AI-Resume] warm-set loaded from $warmSetPath (chat=$($CHAT_MODELS.Count), embed=$($EMBED_MODELS.Count))" -ForegroundColor DarkCyan
    } catch {
        Write-Host "[AI-Resume] WARN: warm-set.json present but unreadable ($($_.Exception.Message)) - using hardcoded defaults" -ForegroundColor Yellow
    }
} else {
    Write-Host "[AI-Resume] no warm-set.json at $warmSetPath - using hardcoded defaults" -ForegroundColor DarkGray
}

# Ollama keep_alive: '5m' = default, '-1' = forever, '0' = unload immediately
$KEEP_ALIVE = '5m'

function Write-Status($msg, $color = 'Cyan') {
    Write-Host "[AI-Resume] $msg" -ForegroundColor $color
}

Write-Status "Pre-warming default models on Master Blaster ..."

# Sanity check - is Ollama responding? The service-start path above already ran,
# so this is a liveness retry, not a second place to start services. The previous
# version called raw Start-Service here with no gate awareness at all, which meant
# this branch could bring Ollama back regardless of what the gate said.
if (-not (Test-OllamaResponding -TimeoutSec 5)) {
    Write-Status "Ollama API not responding yet at $OLLAMA, waiting ..." 'Yellow'
    $alive = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 2
        if (Test-OllamaResponding -TimeoutSec 3) { $alive = $true; break }
    }
    if (-not $alive) {
        Write-Status 'Service is Running but the API never responded. Check OllamaService logs.' 'Red'
        Write-GateLog 'resume failed: service Running but API never responded' 'ERROR'
        exit 1
    }
}

# Treat a connection-refused / cant-connect mid-loop as "service died" and
# abort early - N consecutive 'connection refused' lines would otherwise mask
# the single underlying cause behind a wall of per-model red text.
function Test-ConnectionDown($exception) {
    $msg = $exception.Exception.Message
    return ($msg -match 'actively refused' -or
            $msg -match 'Unable to connect' -or
            $msg -match 'connection.*refused' -or
            $msg -match 'No connection could be made')
}

$failures = @()
$serviceDied = $false

# Warming is the slowest part of the whole gate (up to ~120 s per model). A game
# launched during it would otherwise get a fully-loaded GPU for minutes, so we
# re-check between models and bail out rather than finishing the job.
$abortedForGame = ''
function Test-AbortForGame {
    if ($script:ForceWarm) { return $false }
    $g = Get-RunningGame
    if ($g -ne '' -and $g -ne '?unknown') {
        $script:abortedForGame = $g
        return $true
    }
    return $false
}
$script:ForceWarm = [bool]$Force

foreach ($model in $CHAT_MODELS) {
    if ($serviceDied) { break }
    if (Test-AbortForGame) { break }
    Write-Status "Warming chat:  $model"
    $body = @{
        model      = $model
        prompt     = ''
        stream     = $false
        keep_alive = $KEEP_ALIVE
    } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $body `
            -ContentType 'application/json' -TimeoutSec 120 | Out-Null
        Write-Host "  loaded" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $failures += $model
        if (Test-ConnectionDown $_) {
            Write-Status "Ollama appears to have died mid-warm (connection refused). Aborting remaining models." 'Red'
            $serviceDied = $true
        }
    }
}

foreach ($model in $EMBED_MODELS) {
    if ($serviceDied) { break }
    if (Test-AbortForGame) { break }
    Write-Status "Warming embed: $model"
    $body = @{
        model      = $model
        input      = 'warmup'
        keep_alive = $KEEP_ALIVE
    } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "$OLLAMA/api/embed" -Method Post -Body $body `
            -ContentType 'application/json' -TimeoutSec 120 | Out-Null
        Write-Host "  loaded" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $failures += $model
        if (Test-ConnectionDown $_) {
            Write-Status "Ollama appears to have died mid-warm (connection refused). Aborting remaining models." 'Red'
            $serviceDied = $true
        }
    }
}

Start-Sleep -Seconds 1
Write-Status "Final state:"
$verifyFailed = $false
try {
    $ps = Invoke-RestMethod -Uri "$OLLAMA/api/ps" -TimeoutSec 5
    if ($ps.models -and $ps.models.Count -gt 0) {
        foreach ($m in $ps.models) {
            if ($null -eq $m.PSObject.Properties['size_vram']) {
                $vramDisplay = '?'
            } else {
                $vramDisplay = "$([math]::Round($m.size_vram / 1MB, 0)) MB"
            }
            Write-Host ("  - {0} ({1} VRAM)" -f $m.name, $vramDisplay) -ForegroundColor Green
        }
    } else {
        Write-Host "  (no models loaded)" -ForegroundColor Yellow
    }
} catch {
    Write-Status "Could not verify final state: $($_.Exception.Message)" 'Red'
    $verifyFailed = $true
}

if ($script:abortedForGame -ne '') {
    # A game launched while we were warming. Hand the GPU straight back rather
    # than leaving models resident, and let the watcher take it from here.
    Write-Status "'$($script:abortedForGame)' launched during warm-up - releasing the GPU again." 'Yellow'
    Write-GateLog "resume aborted mid-warm, '$($script:abortedForGame)' launched" 'WARN'
    if (Stop-OllamaHard) {
        Set-GateState -State 'paused' -Owner $script:OWNER_GAME `
            -Reason "game launched during warm-up: $($script:abortedForGame)" `
            -Game $script:abortedForGame | Out-Null
    }
    exit 4
}

if ($serviceDied) {
    Write-Status "Service died during warm-up - investigate OllamaService logs." 'Red'
    Write-GateLog 'resume failed: service died during warm-up' 'ERROR'
    exit 1
}
if ($failures.Count -gt 0) {
    Write-Status "Some models failed to load: $($failures -join ', ')" 'Red'
    # The service IS up, so the node can still serve the fleet even though the
    # warm set is incomplete. Release the gate rather than stranding the node,
    # but exit non-zero so callers and the log record the degraded state.
    Set-GateState -State 'available' -Owner '' -Reason "resumed with warm failures: $($failures -join ', ')" | Out-Null
    Write-GateLog "resume completed but these models failed to warm: $($failures -join ', ')" 'WARN'
    exit 1
}
if ($verifyFailed) {
    Write-Status "Warmed without errors but could NOT confirm models actually loaded." 'Red'
    Write-GateLog 'resume could not verify loaded models' 'WARN'
    exit 1
}

Set-GateState -State 'available' -Owner '' -Reason 'resumed and warm' | Out-Null
Write-GateLog 'resume complete, node available to the fleet'
Write-Status "Ready." 'Green'
exit 0

} finally {
    # Released on every exit path, including the `exit N` calls above.
    Exit-GateLock
}
