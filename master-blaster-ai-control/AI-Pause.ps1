# AI-Pause.ps1 - release Master Blaster's GPU for gaming
# Unloads every model currently in Ollama's VRAM via keep_alive=0.
# Service stays up; first request after pause will reload (slow).

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'

function Write-Status($msg, $color = 'Cyan') {
    Write-Host "[AI-Pause] $msg" -ForegroundColor $color
}

Write-Status "Querying loaded models on $OLLAMA ..."

try {
    $ps = Invoke-RestMethod -Uri "$OLLAMA/api/ps" -TimeoutSec 5
} catch {
    Write-Status "FAILED: Ollama API not responding at $OLLAMA" 'Red'
    $svc = Get-Service -Name 'OllamaService' -ErrorAction SilentlyContinue
    if ($svc) { Write-Status "OllamaService status: $($svc.Status)" 'Yellow' }
    Write-Status "Error: $($_.Exception.Message)" 'Red'
    exit 1
}

if (-not $ps.models -or $ps.models.Count -eq 0) {
    Write-Status "No models currently loaded. Nothing to do." 'Green'
    exit 0
}

Write-Status "Found $($ps.models.Count) loaded model(s):"
foreach ($m in $ps.models) {
    # Distinguish "field absent" (API drift) from "zero VRAM" (CPU-only).
    if ($null -eq $m.PSObject.Properties['size_vram']) {
        $vramDisplay = '?'
    } else {
        $vramDisplay = "$([math]::Round($m.size_vram / 1MB, 0)) MB"
    }
    Write-Host ("  - {0} ({1} VRAM)" -f $m.name, $vramDisplay)
}

$failures = @()
foreach ($m in $ps.models) {
    Write-Status "Unloading $($m.name) ..."
    $body = @{ model = $m.name; keep_alive = 0 } | ConvertTo-Json -Compress
    $unloaded = $false

    # Try /api/generate first (works for chat models and most embedding models)
    try {
        Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $body `
            -ContentType 'application/json' -TimeoutSec 10 | Out-Null
        $unloaded = $true
    } catch {
        $genErr = $_.Exception.Message
        # Fallback: /api/embed for pure embedding models
        try {
            Invoke-RestMethod -Uri "$OLLAMA/api/embed" -Method Post -Body $body `
                -ContentType 'application/json' -TimeoutSec 10 | Out-Null
            $unloaded = $true
        } catch {
            $failures += [pscustomobject]@{ model = $m.name; gen = $genErr; embed = $_.Exception.Message }
        }
    }
}

# Ollama evicts asynchronously after the unload call returns; poll up to ~15 s
# for an empty /api/ps. Empirically takes 3-5 s on this box for a 2.4 GB model.
$deadline = (Get-Date).AddSeconds(15)
$verify = $null
while ((Get-Date) -lt $deadline) {
    try {
        $verify = Invoke-RestMethod -Uri "$OLLAMA/api/ps" -TimeoutSec 5
    } catch {
        Write-Status "Could not verify final state: $($_.Exception.Message)" 'Yellow'
        exit 1
    }
    if (-not $verify.models -or $verify.models.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
}

# Always surface per-model unload errors if any occurred - don't gate on verify
# state, because Ollama can evict-anyway-on-timeout and mask the underlying
# cause (auth, 500, OOM, malformed body).
if ($failures.Count -gt 0) {
    Write-Status "Unload errors detected (both endpoints failed):" 'Red'
    foreach ($f in $failures) {
        Write-Host "  $($f.model)" -ForegroundColor Red
        Write-Host "    /api/generate: $($f.gen)"
        Write-Host "    /api/embed:    $($f.embed)"
    }
}

if ($verify.models -and $verify.models.Count -gt 0) {
    Write-Status "WARNING: $($verify.models.Count) model(s) still loaded after 15 s poll:" 'Yellow'
    foreach ($m in $verify.models) { Write-Host "  - $($m.name)" -ForegroundColor Yellow }
    exit 2
}

if ($failures.Count -gt 0) {
    # Verify says clean, but some unload calls errored - Ollama evicted anyway.
    # Surface non-zero exit so cron / chained scripts can react.
    Write-Status "Models evicted, but unload calls had errors (see above). GPU released." 'Yellow'
    exit 3
}

Write-Status "All models unloaded. GPU released for gaming." 'Green'
exit 0
