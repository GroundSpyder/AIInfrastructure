# GpuGate.ps1 - shared state helpers for Master Blaster's GPU gate.
#
# Dot-source this from Game-Watch.ps1, AI-Pause.ps1 and AI-Resume.ps1 so all
# three agree on a single source of truth about who owns the GPU right now.
#
# Why a state file at all: before this existed, AI-Pause was a one-shot unload
# and Ollama reloaded a ~9 GB model on the very next inbound request (the fleet
# gateway load-balances fleet/embed onto this box, so that happened within
# minutes, mid-game). The gate makes a pause STICKY: the service is stopped,
# and nothing brings it back until the owner of the pause releases it.
#
# State lives in ProgramData, not the repo, because the watcher runs as SYSTEM
# while the hotkey scripts and the AI Fleet Dashboard (over SSH) run as Kyle.
# Mixed ownership inside a git working tree causes permission surprises.

Set-StrictMode -Version 2.0

$script:GateDir   = Join-Path $env:ProgramData 'falkensteink'
$script:GatePath  = Join-Path $script:GateDir 'gpu-gate.json'
$script:GateLog   = Join-Path $script:GateDir 'gpu-gate.log'
$script:ServiceNm = 'OllamaService'
$script:OllamaUrl = 'http://localhost:11434'

# Pause owners. The watcher will only auto-resume a pause it created itself.
# A manual pause outranks the watcher so that pressing the hotkey is always
# respected, even if no game is detected.
$script:OWNER_GAME   = 'game'
$script:OWNER_MANUAL = 'manual'

$script:MutexName = 'Global\falkensteink-gpu-gate'
$script:Mutex     = $null

function Enter-GateLock {
    <#
      Serialise every read-modify-write of the gate across processes.

      Without this, the SYSTEM watcher and an interactive hotkey run concurrently
      and interleave badly. The dangerous sequence: the watcher decides to resume
      (game not yet running), Kyle launches a game and hits pause, then the
      watcher's Start-Service lands afterwards - leaving the service RUNNING with
      the gate recorded as paused, 11 GB in VRAM, mid-game.

      Returns $true if the lock was taken. On failure we deliberately return
      $false rather than proceeding unlocked, and callers skip the cycle: missing
      one 10-second poll is harmless, corrupting the gate is not.
    #>
    param([int]$TimeoutMs = 20000)
    try {
        if ($null -eq $script:Mutex) {
            $script:Mutex = New-Object System.Threading.Mutex($false, $script:MutexName)
        }
        return $script:Mutex.WaitOne($TimeoutMs)
    } catch [System.Threading.AbandonedMutexException] {
        # A holder died without releasing. We now own it; that is recoverable,
        # but it means some other process crashed mid-transition - say so.
        Write-GateLog 'gate mutex was abandoned by a crashed process; recovered ownership' 'WARN'
        return $true
    } catch {
        Write-GateLog "could not acquire gate mutex: $($_.Exception.Message)" 'ERROR'
        return $false
    }
}

function Exit-GateLock {
    if ($null -eq $script:Mutex) { return }
    try {
        $script:Mutex.ReleaseMutex()
    } catch {
        Write-GateLog "could not release gate mutex: $($_.Exception.Message)" 'WARN'
    }
}

function Initialize-GateDir {
    if (-not (Test-Path -LiteralPath $script:GateDir)) {
        New-Item -ItemType Directory -Path $script:GateDir -Force | Out-Null
    }
}

# --------------------------------------------------------------- game detection
# Lives here rather than in Game-Watch.ps1 so AI-Resume.ps1 can ask the same
# question. AI-Resume used to guard on the gate's OWNER field, which meant that
# after a manual pause, pressing Ctrl+Alt+R while a game was running warmed 11 GB
# into VRAM without complaint - the single most likely way to lose a session.

function Get-Watchlist {
    <#
      Returns a string[] of process-name patterns, or $null when the list could
      not be read. $null is meaningfully different from an empty list: empty
      means "no games configured", $null means "we do not know", and callers
      treat not-knowing as game-running (fail-safe toward gaming).
    #>
    $path = Join-Path $PSScriptRoot 'games.json'
    if (-not (Test-Path -LiteralPath $path)) {
        Write-GateLog "watchlist missing at $path" 'ERROR'
        return $null
    }
    try {
        $cfg = Get-Content -Raw -LiteralPath $path -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if (-not ($cfg.PSObject.Properties.Name -contains 'processes')) {
            throw "no 'processes' array in watchlist"
        }
        return @($cfg.processes | Where-Object { $_ -and $_ -notmatch '^_' })
    } catch {
        Write-GateLog "watchlist unreadable: $($_.Exception.Message)" 'ERROR'
        return $null
    }
}

function Test-NameMatches {
    param([string]$ProcessName, [string[]]$Patterns)
    foreach ($p in $Patterns) {
        if ($p.EndsWith('*')) {
            $prefix = $p.Substring(0, $p.Length - 1)
            if ($ProcessName -like "$prefix*") { return $true }
        } elseif ($ProcessName -eq $p) {
            return $true
        }
    }
    return $false
}

function Get-RunningGame {
    <#
      Returns the matched process name, '' when nothing matches, or the sentinel
      '?unknown' when we could not evaluate. Callers must treat '?unknown' as
      "a game may be running".
    #>
    $patterns = Get-Watchlist
    if ($null -eq $patterns) { return '?unknown' }
    if ($patterns.Count -eq 0) { return '' }
    try {
        foreach ($proc in (Get-Process -ErrorAction SilentlyContinue)) {
            if (Test-NameMatches -ProcessName $proc.ProcessName -Patterns $patterns) {
                return $proc.ProcessName
            }
        }
        return ''
    } catch {
        Write-GateLog "process enumeration failed: $($_.Exception.Message)" 'ERROR'
        return '?unknown'
    }
}

function Write-GateLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Level = 'INFO'
    )
    Initialize-GateDir
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $line  = "$stamp [$Level] $Message"
    try {
        Add-Content -LiteralPath $script:GateLog -Value $line -Encoding utf8 -ErrorAction Stop
    } catch {
        # Logging must never take the gate down. Surface to the console instead
        # of swallowing, so an interactive run still shows the problem.
        Write-Host "[gpu-gate] WARN could not write log: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    # Keep the log bounded. This runs unattended for weeks at a time.
    try {
        $info = Get-Item -LiteralPath $script:GateLog -ErrorAction Stop
        if ($info.Length -gt 2MB) {
            $keep = Get-Content -LiteralPath $script:GateLog -Tail 2000
            Set-Content -LiteralPath $script:GateLog -Value $keep -Encoding utf8
        }
    } catch {
        Write-Host "[gpu-gate] WARN could not rotate log: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function Get-GateState {
    <#
      Returns a PSCustomObject with: state (available|paused), owner, reason,
      game, since. A missing or corrupt file is reported as 'available' with a
      logged warning, never as a silent default, because "we could not read the
      gate" and "the gate says go" are different facts.
    #>
    if (-not (Test-Path -LiteralPath $script:GatePath)) {
        return [pscustomobject]@{
            state = 'available'; owner = ''; reason = 'no state file'
            game = ''; since = ''
        }
    }
    try {
        $raw = Get-Content -Raw -LiteralPath $script:GatePath -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) { throw 'state file is empty' }
        $obj = $raw | ConvertFrom-Json -ErrorAction Stop
        foreach ($f in @('state', 'owner', 'reason', 'game', 'since')) {
            if (-not ($obj.PSObject.Properties.Name -contains $f)) {
                Add-Member -InputObject $obj -NotePropertyName $f -NotePropertyValue '' -Force
            }
        }
        if ($obj.state -ne 'paused' -and $obj.state -ne 'available') {
            throw "unrecognised state value '$($obj.state)'"
        }
        return $obj
    } catch {
        Write-GateLog "gate state unreadable ($($_.Exception.Message)); treating as AVAILABLE" 'WARN'
        return [pscustomobject]@{
            state = 'available'; owner = ''; reason = "unreadable: $($_.Exception.Message)"
            game = ''; since = ''
        }
    }
}

function Set-GateState {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('available', 'paused')][string]$State,
        [string]$Owner  = '',
        [string]$Reason = '',
        [string]$Game   = ''
    )
    $payload = [pscustomobject]@{
        state  = $State
        owner  = $Owner
        reason = $Reason
        game   = $Game
        since  = (Get-Date).ToString('o')
    }
    try {
        Initialize-GateDir
        $tmp = "$script:GatePath.tmp"
        $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $tmp -Encoding utf8

        if (Test-Path -LiteralPath $script:GatePath) {
            # File.Replace is a genuine atomic swap. Move-Item -Force is a
            # delete-then-rename, which leaves a window where the gate file does
            # not exist at all - and Get-GateState reads a missing file as
            # 'available'. A hotkey landing in that window would silently pass
            # the game guard, which is exactly the failure this gate exists to
            # prevent.
            #
            # The backup path is NOT optional here: .NET Framework's Replace
            # calls GetFullPath on the backup argument before checking it for
            # null, so passing $null throws "The path is not of a legal form."
            # Verified empirically on this box 2026-07-30.
            $bak = "$($script:GatePath).bak"
            [System.IO.File]::Replace($tmp, $script:GatePath, $bak)
            Remove-Item -LiteralPath $bak -Force -ErrorAction SilentlyContinue
        } else {
            Move-Item -LiteralPath $tmp -Destination $script:GatePath -Force
        }
    } catch {
        # A gate we cannot persist is a gate that will not hold across processes.
        # Never let this pass quietly.
        Write-GateLog "FAILED to persist gate state ($State/$Owner): $($_.Exception.Message)" 'ERROR'
        throw
    }
    return $payload
}

function Get-OllamaService {
    return (Get-Service -Name $script:ServiceNm -ErrorAction SilentlyContinue)
}

function Stop-OllamaHard {
    <#
      Stops the service outright. This is the whole point of the redesign:
      unloading models via keep_alive=0 does not hold, because any inbound
      request reloads them. A stopped service refuses the connection, which
      also lets the LiteLLM gateway cooldown this backend cleanly instead of
      retrying against a half-alive node.
    #>
    $svc = Get-OllamaService
    if ($null -eq $svc) {
        Write-GateLog "cannot stop: service '$script:ServiceNm' not found" 'ERROR'
        return $false
    }
    if ($svc.Status -ne 'Stopped') {
        try {
            Stop-Service -Name $script:ServiceNm -Force -ErrorAction Stop
            (Get-Service -Name $script:ServiceNm).WaitForStatus('Stopped', '00:00:30')
        } catch {
            Write-GateLog "failed to stop service: $($_.Exception.Message)" 'ERROR'
            return $false
        }
    }

    # "Service is Stopped" and "the GPU is free" are different facts. A stray
    # `ollama serve` started outside the service, or a wedged shutdown, keeps
    # port 11434 answering and VRAM held. Verify rather than assume.
    Start-Sleep -Milliseconds 500
    if (Test-OllamaResponding -TimeoutSec 3) {
        Write-GateLog 'service reports Stopped but port 11434 still answers - GPU is NOT free' 'ERROR'
        return $false
    }

    Write-GateLog 'OllamaService stopped, GPU released'
    return $true
}

function Start-OllamaHard {
    $svc = Get-OllamaService
    if ($null -eq $svc) {
        Write-GateLog "cannot start: service '$script:ServiceNm' not found" 'ERROR'
        return $false
    }
    if ($svc.Status -eq 'Running') { return $true }
    try {
        Start-Service -Name $script:ServiceNm -ErrorAction Stop
        (Get-Service -Name $script:ServiceNm).WaitForStatus('Running', '00:00:30')
        Write-GateLog 'OllamaService started'
        return $true
    } catch {
        Write-GateLog "failed to start service: $($_.Exception.Message)" 'ERROR'
        return $false
    }
}

function Publish-GateState {
    <#
      Announce this box's gate state to the Reaper dashboard on Toshi.

      Why this exists: from Toshi's side, "Ollama is gated for gaming" and
      "Master Blaster's PSU died" look identical - both are a refused
      connection. Without a heartbeat we would have to choose between alarming
      on every gaming session (noise) or never alarming at all (a blind spot).

      With it, Reaper can tell the two apart: a recent heartbeat saying "paused"
      means away-by-design; silence means genuinely unreachable, which IS worth
      alerting on. Ollama's own port is closed while gated, so the heartbeat has
      to be pushed rather than polled.

      Best-effort by design. Toshi being unreachable must never stop us from
      releasing the GPU for a game, so failures are logged and swallowed here
      rather than propagated. The consequence of a lost heartbeat is a false
      "down" on a dashboard, not a stuck GPU.
    #>
    param(
        [Parameter(Mandatory = $true)][ValidateSet('available', 'paused')][string]$State,
        [string]$Owner  = '',
        [string]$Reason = '',
        [string]$Game   = '',
        # Set when the gate is in a state that needs a human. Reaper surfaces
        # this on /api/node-health so it can reach Kuma and the dashboard - the
        # gate log lives on a headless SYSTEM task and nothing tails it, so
        # without this an ERROR disposition would reach nobody.
        [string]$Alert  = ''
    )
    $url = $env:REAPER_GATE_URL
    if ([string]::IsNullOrWhiteSpace($url)) { $url = 'http://192.168.4.31:8793/api/gate' }

    $body = @{
        node   = 'master-blaster'
        state  = $State
        owner  = $Owner
        reason = $Reason
        game   = $Game
        alert  = $Alert
    } | ConvertTo-Json -Compress

    try {
        Invoke-RestMethod -Uri $url -Method Post -Body $body `
            -ContentType 'application/json' -TimeoutSec 5 | Out-Null
        return $true
    } catch {
        Write-GateLog "gate heartbeat to $url failed: $($_.Exception.Message)" 'WARN'
        return $false
    }
}

function Test-OllamaStopped {
    <#
      Ground truth for "is the GPU free of Ollama": the service is Stopped AND
      nothing is answering on the port. Returns $true, $false, or $null when the
      service cannot be queried at all (caller should treat $null as not-stopped,
      per the fail-safe-toward-gaming rule).
    #>
    $svc = Get-OllamaService
    if ($null -eq $svc) { return $null }
    if ($svc.Status -ne 'Stopped') { return $false }
    if (Test-OllamaResponding -TimeoutSec 2) { return $false }
    return $true
}

function Test-OllamaResponding {
    param([int]$TimeoutSec = 5)
    try {
        Invoke-RestMethod -Uri "$script:OllamaUrl/api/version" -TimeoutSec $TimeoutSec | Out-Null
        return $true
    } catch {
        return $false
    }
}
