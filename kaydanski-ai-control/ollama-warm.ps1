# ollama-warm.ps1 - warm Kaydanski's default models into VRAM
# Peer to master-blaster-ai-control/AI-Resume.ps1; same shape, different
# defaults (Kaydanski's RX 6600 has 8 GB VRAM and runs Vulkan, so the
# warm set is lighter than MB's RX 9070 XT / ROCm box).
#
# Reads C:\Users\Kaiden\ollama-warm-set.json if present (this is what
# the AI Fleet Dashboard writes via SSH when Kyle edits the warm-set in
# the GUI - see Birdmug-AI-Fleet-Dashboard/server/models_api.py
# WARM_SET_PATH['kaydanski']). Falls back to hardcoded defaults if the
# file is missing or corrupt so the box can still boot warm.

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'

# Defaults for Kaydanski (RX 6600 / 8 GB VRAM / Vulkan backend).
# qwen2.5:7b chat + bge-m3 embed = ~5 GB resident, leaves ~3 GB for KV
# cache. Heavier models (qwen3:30b-a3b) don't fit and run CPU.
$CHAT_MODELS  = @('qwen2.5:7b')
$EMBED_MODELS = @('bge-m3:latest')

# Keep-alive default; Ollama treats '-1' as forever and '0' as evict-on-idle.
$KEEP_ALIVE = '5m'

# Warm-set override path. Canonical with models_api.py WARM_SET_PATH.
$warmSetPath = "$env:USERPROFILE\ollama-warm-set.json"
if (Test-Path -LiteralPath $warmSetPath) {
    try {
        $warmSet = Get-Content -Raw -LiteralPath $warmSetPath | ConvertFrom-Json
        if ($warmSet.chat -is [array] -and $warmSet.chat.Count -ge 0) {
            $CHAT_MODELS = @($warmSet.chat)
        }
        if ($warmSet.embed -is [array] -and $warmSet.embed.Count -ge 0) {
            $EMBED_MODELS = @($warmSet.embed)
        }
        Write-Host "[ollama-warm] warm-set loaded from $warmSetPath (chat=$($CHAT_MODELS.Count), embed=$($EMBED_MODELS.Count))" -ForegroundColor DarkCyan
    } catch {
        Write-Host "[ollama-warm] WARN: warm-set.json present but unreadable ($($_.Exception.Message)) - using hardcoded defaults" -ForegroundColor Yellow
    }
} else {
    Write-Host "[ollama-warm] no warm-set.json at $warmSetPath - using hardcoded defaults" -ForegroundColor DarkGray
}

function Write-Status($msg, $color = 'Cyan') {
    Write-Host "[ollama-warm] $msg" -ForegroundColor $color
}

Write-Status "Pre-warming default models on Kaydanski ..."

# Sanity check - is Ollama responding?
try {
    Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 5 | Out-Null
} catch {
    Write-Status "FAILED: Ollama API not responding at $OLLAMA" 'Red'
    Write-Status "ollama-start.ps1 runs at logon; check that scheduled task fired and look at $env:USERPROFILE\ollama-logs\serve-*.log" 'Yellow'
    exit 1
}

function Test-ConnectionDown($exception) {
    $msg = $exception.Exception.Message
    return ($msg -match 'actively refused' -or
            $msg -match 'Unable to connect' -or
            $msg -match 'connection.*refused' -or
            $msg -match 'No connection could be made')
}

$failures = @()
$serviceDied = $false

foreach ($model in $CHAT_MODELS) {
    if ($serviceDied) { break }
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

if ($serviceDied) {
    Write-Status "Service died during warm-up - investigate Ollama logs at $env:USERPROFILE\ollama-logs\" 'Red'
    exit 1
}
if ($failures.Count -gt 0) {
    Write-Status "Some models failed to load: $($failures -join ', ')" 'Red'
    exit 1
}
if ($verifyFailed) {
    Write-Status "Warmed without errors but could NOT confirm models actually loaded." 'Red'
    exit 1
}

Write-Status "Ready." 'Green'
exit 0
