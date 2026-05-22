# AI-Resume.ps1 - warm Master Blaster's default models back into VRAM
# Run after closing a game; mirrors what Ollama would do lazily on first request,
# but front-loads the slow load so the next real call is fast.

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'

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

# Sanity check - is Ollama responding?
try {
    Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 5 | Out-Null
} catch {
    Write-Status "FAILED: Ollama API not responding at $OLLAMA" 'Red'
    $svc = Get-Service -Name 'OllamaService' -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Status "OllamaService status: $($svc.Status)" 'Yellow'
        if ($svc.Status -ne 'Running') {
            Write-Status "Attempting to start OllamaService ..." 'Yellow'
            try {
                Start-Service -Name 'OllamaService' -ErrorAction Stop
                Start-Sleep -Seconds 3
                Write-Status "Service started, retrying ..." 'Yellow'
                Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 10 | Out-Null
            } catch {
                Write-Status "Could not start OllamaService: $($_.Exception.Message)" 'Red'
                exit 1
            }
        } else {
            Write-Status "Service is Running but API not responding. Check logs." 'Red'
            exit 1
        }
    } else {
        Write-Status "OllamaService not found." 'Red'
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
    Write-Status "Service died during warm-up - investigate OllamaService logs." 'Red'
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
