# Game-Watch.ps1 - automatic GPU gate for Master Blaster.
#
# Watches for game processes and stops OllamaService while one is running, then
# restarts and re-warms it after the game exits. Runs unattended as SYSTEM via
# a scheduled task (see Install-GameWatch.ps1).
#
# Background: the fleet's LiteLLM gateway load-balances fleet/embed across
# Kaydanski AND this box, and fleet/chat-quality points here exclusively. That
# means ordinary fleet traffic pulls qwen3:14b (~9 GB) plus bge-m3 (~1.2 GB)
# into a 16 GB card with no idea a game is running. The old AI-Pause.ps1 only
# unloaded models, and its own header admitted the next request would reload
# them. This watcher is the sticky gate that makes local AI and gaming coexist.
#
# FAIL-SAFE DIRECTION: every uncertain path here favours GAMING, not the fleet.
# If the watchlist is unreadable, if a poll throws, or if the watcher is killed
# outright, Ollama stays stopped. The cost of that is a delayed reindex. The
# cost of the opposite is a stuttering game, which is the whole problem we are
# solving.
#
# Usage:
#   Game-Watch.ps1                 run the watch loop (what the task does)
#   Game-Watch.ps1 -Status         print current gate state and exit
#   Game-Watch.ps1 -Once           evaluate once and exit (useful for testing)
#   Game-Watch.ps1 -Candidates     list running processes that look like games

[CmdletBinding()]
param(
    [int]$IntervalSeconds     = 10,
    [int]$ResumeGraceSeconds  = 60,
    [switch]$Once,
    [switch]$Status,
    [switch]$Candidates
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'GpuGate.ps1')

$script:WatchlistPath = Join-Path $PSScriptRoot 'games.json'
$script:ResumeScript  = Join-Path $PSScriptRoot 'AI-Resume.ps1'

# Get-Watchlist / Test-NameMatches / Get-RunningGame now live in GpuGate.ps1 so
# that AI-Resume.ps1 can ask the same question before it warms 11 GB into VRAM.

function Invoke-Warm {
    # Re-warming is best-effort. A failed warm must not leave the gate stuck in
    # 'paused', or the fleet never gets this node back. We log loudly instead.
    if (-not (Test-Path -LiteralPath $script:ResumeScript)) {
        Write-GateLog "AI-Resume.ps1 not found at $script:ResumeScript, service started cold" 'WARN'
        return
    }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script:ResumeScript -Force 2>&1 |
            ForEach-Object { Write-GateLog "warm: $_" }
        if ($LASTEXITCODE -ne 0) {
            Write-GateLog "AI-Resume exited $LASTEXITCODE, models may not be warm" 'WARN'
        }
    } catch {
        Write-GateLog "warm-up threw: $($_.Exception.Message)" 'WARN'
    }
}

function Suspend-ForGame {
    param([string]$GameName)
    Write-GateLog "game detected: $GameName - releasing GPU"
    $ok = Stop-OllamaHard

    # Verify the GPU is actually free rather than trusting the service state.
    # "Service stopped" and "nothing is holding VRAM" are different facts - a
    # stray `ollama serve` outside the service, or a wedged shutdown, breaks the
    # equivalence. AI-Pause.ps1 has always checked this; the unattended path
    # runs far more often and needs it more.
    if ($ok) {
        Start-Sleep -Milliseconds 500
        if (Test-OllamaResponding -TimeoutSec 3) {
            Write-GateLog "service reports stopped but port 11434 still answers - GPU may still be held" 'ERROR'
            $ok = $false
        }
    }

    if ($ok) {
        Set-GateState -State 'paused' -Owner $script:OWNER_GAME `
            -Reason "game running: $GameName" -Game $GameName | Out-Null
        return
    }

    # CRITICAL: do NOT record 'paused' when the stop failed. The evaluation loop
    # skips Suspend-ForGame whenever state is already 'paused', so writing it
    # here would mean we never retry for the rest of the gaming session while
    # the state file cheerfully claims the GPU was released. Leaving the state
    # at its current value keeps the retry condition true on the next poll.
    Write-GateLog "GPU NOT released - OllamaService failed to stop while '$GameName' is running; will retry next poll" 'ERROR'
    Publish-GateState -State 'available' -Owner $script:OWNER_GAME `
        -Reason "FAILED to stop Ollama while '$GameName' is running" -Game $GameName `
        -Alert "Could not stop OllamaService while '$GameName' is running. The GPU is still held by Ollama." | Out-Null
}

function Resume-AfterGame {
    # $Trigger names why we are starting the service, and is recorded in the gate
    # state so "came back after a game" and "was found down for no reason" are
    # distinguishable afterwards. They have very different causes.
    param([string]$Trigger = 'game exited')

    # Re-check immediately before starting. The decision to resume was made from
    # a snapshot taken earlier in this evaluation, and a game can launch in
    # between. Starting the service on a stale snapshot is how the watcher ends
    # up loading 11 GB into VRAM seconds after Kyle has entered a match.
    $gameNow = Get-RunningGame
    if ($gameNow -ne '') {
        Write-GateLog "resume aborted - '$gameNow' appeared while we were deciding"
        return
    }

    Write-GateLog 'no game running - restoring Ollama'
    if (-not (Start-OllamaHard)) {
        # Leave the gate paused. Reporting 'available' when the service did not
        # actually start would tell the fleet to route traffic into a black hole.
        Write-GateLog 'service failed to start; leaving gate PAUSED so the fleet keeps failing over' 'ERROR'
        Publish-GateState -State 'paused' -Owner $script:OWNER_GAME -Reason "service failed to start ($Trigger)" `
            -Alert "OllamaService will not start ($Trigger). This node is out of the fleet until fixed." | Out-Null
        return
    }

    # A service in state Running is not proof Ollama is serving. AI-Resume.ps1
    # already knows the "Running but API not responding" state exists; if we
    # flipped the gate to 'available' on service state alone we would hand the
    # fleet a black hole and only whisper about it in a local log.
    $responding = $false
    for ($i = 0; $i -lt 10; $i++) {
        if (Test-OllamaResponding -TimeoutSec 3) { $responding = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $responding) {
        Write-GateLog 'service is Running but the Ollama API never responded; leaving gate PAUSED' 'ERROR'
        return
    }

    Set-GateState -State 'available' -Owner '' -Reason $Trigger | Out-Null
    Invoke-Warm
    Write-GateLog 'gate released, fleet node back online'
}

# ---------------------------------------------------------------- entry points

if ($Candidates) {
    $patterns = Get-Watchlist
    if ($null -eq $patterns) { $patterns = @() }
    Write-Host 'Running processes using meaningful memory (possible games):' -ForegroundColor Cyan
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.WorkingSet64 -gt 300MB } |
        Sort-Object WorkingSet64 -Descending |
        Select-Object -First 25 |
        ForEach-Object {
            $watched = Test-NameMatches -ProcessName $_.ProcessName -Patterns $patterns
            if ($watched) { $mark = '[watched]' } else { $mark = '          ' }
            $mb = [math]::Round($_.WorkingSet64 / 1MB, 0)
            Write-Host ("  {0} {1,-32} {2,6} MB" -f $mark, $_.ProcessName, $mb)
        }
    Write-Host ''
    Write-Host "Add any of these to the 'processes' array in $script:WatchlistPath" -ForegroundColor DarkGray
    exit 0
}

if ($Status) {
    $g   = Get-GateState
    $svc = Get-OllamaService
    if ($null -eq $svc) { $svcStatus = 'NOT INSTALLED' } else { $svcStatus = $svc.Status }
    Write-Host "gate state : $($g.state)"      -ForegroundColor Cyan
    Write-Host "owner      : $($g.owner)"
    Write-Host "reason     : $($g.reason)"
    Write-Host "since      : $($g.since)"
    Write-Host "service    : $svcStatus"
    if (Test-OllamaResponding) { $api = 'responding' } else { $api = 'not responding' }
    Write-Host "ollama api : $api"
    exit 0
}

function Invoke-GateEvaluation {
    param([ref]$LastGameSeenAt)

    $game = Get-RunningGame
    $gate = Get-GateState

    # Heartbeat every poll, not just on transitions. Toshi treats a stale
    # heartbeat as "genuinely unreachable" rather than "away", so a steady pulse
    # is what keeps a long gaming session from looking like an outage.
    Publish-GateState -State $gate.state -Owner $gate.owner `
        -Reason $gate.reason -Game $gate.game | Out-Null

    if ($game -eq '?unknown') {
        # Could not tell. Fail toward gaming: assert the service is stopped.
        if ((Test-OllamaStopped) -ne $true) {
            Write-GateLog 'cannot determine game state - pausing as a precaution' 'WARN'
            Suspend-ForGame -GameName 'unknown'
        }
        return
    }

    if ($game -ne '') {
        $LastGameSeenAt.Value = Get-Date

        # LEVEL-TRIGGERED, not edge-triggered. The old version only acted when
        # the gate file said something other than 'paused', which meant anything
        # that started Ollama behind the gate's back was permanent for the rest
        # of the session: the Fleet Dashboard's "Restart OllamaService" button,
        # `nssm restart`, or simply a reboot with the service set to Automatic.
        # The gate file records intent; the service is ground truth. Assert it.
        if ((Test-OllamaStopped) -ne $true) {
            Suspend-ForGame -GameName $game
        } elseif ($gate.state -ne 'paused' -or $gate.game -ne $game) {
            # Service is already correctly stopped; just keep the record honest
            # so /api/status and the log show what is actually holding the GPU.
            Set-GateState -State 'paused' -Owner $script:OWNER_GAME `
                -Reason "game running: $game" -Game $game | Out-Null
        }
        return
    }

    # No game running.
    if ($gate.state -ne 'paused') {
        # LEVEL-TRIGGERED on the start side too, for the same reason the stop side
        # is: the gate file records intent, the service is ground truth, and the
        # two drift. Without this the watcher only ever starts Ollama on the
        # edge out of 'paused', so "gate available, no game, service stopped" is
        # a state nothing repairs - it just sits there.
        #
        # That is not hypothetical. Master Blaster rebooted on 2026-08-12,
        # OllamaService is StartMode=Manual so nothing brought it back, and the
        # gate went on reporting 'available / resumed and warm' for two days
        # while every Squire intake silently failed to classify. Found
        # 2026-08-13; see Squire/memory/lessons_learned.md.
        #
        # A deliberate pause is always state='paused' (AI-Pause records it that
        # way), so reaching here with the service down means nobody asked for it
        # to be down.
        if ((Test-OllamaStopped) -eq $true) {
            Write-GateLog 'gate is available and no game is running, but OllamaService is stopped - restoring' 'WARN'
            Resume-AfterGame -Trigger 'found stopped with the gate available'
            $LastGameSeenAt.Value = $null
        }
        return
    }

    if ($gate.owner -eq $script:OWNER_MANUAL) {
        # Kyle paused this by hand. Only Kyle releases it.
        return
    }

    $since = $LastGameSeenAt.Value
    if ($null -ne $since) {
        $elapsed = ((Get-Date) - $since).TotalSeconds
        if ($elapsed -lt $ResumeGraceSeconds) { return }
    }
    Resume-AfterGame
    $LastGameSeenAt.Value = $null
}

function Invoke-GateEvaluationLocked {
    <#
      Every read-modify-write of the gate happens under the cross-process mutex,
      so the watcher and an interactive AI-Pause/AI-Resume can never interleave
      into "service running, gate says paused".
    #>
    param([ref]$LastGameSeenAt)

    if (-not (Enter-GateLock)) {
        Write-GateLog 'skipping poll - could not take the gate lock' 'WARN'
        return
    }
    try {
        Invoke-GateEvaluation -LastGameSeenAt $LastGameSeenAt
    } finally {
        Exit-GateLock
    }
}

$lastGameSeenAt = $null

if ($Once) {
    Invoke-GateEvaluationLocked -LastGameSeenAt ([ref]$lastGameSeenAt)
    exit 0
}

Write-GateLog "watcher started (interval=${IntervalSeconds}s grace=${ResumeGraceSeconds}s)"

# Evaluate immediately on startup so a game already running at logon is honoured
# before Ollama has a chance to warm into VRAM.
while ($true) {
    try {
        Invoke-GateEvaluationLocked -LastGameSeenAt ([ref]$lastGameSeenAt)
    } catch {
        # Never let one bad poll kill the loop, but never silently continue
        # either. Log it, and pause if we are not already paused, because an
        # unhealthy watcher must not be the reason a game stutters.
        Write-GateLog "poll failed: $($_.Exception.Message)" 'ERROR'
        try {
            # Level-triggered like the main path: what matters is whether Ollama
            # is actually holding the GPU, not what the state file claims.
            if ((Test-OllamaStopped) -ne $true) {
                Suspend-ForGame -GameName 'watcher-error'
            }
        } catch {
            Write-GateLog "could not apply fail-safe pause: $($_.Exception.Message)" 'ERROR'
        }
    }
    Start-Sleep -Seconds $IntervalSeconds
}
