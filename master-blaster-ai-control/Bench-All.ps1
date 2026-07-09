# Bench-All.ps1 - benchmark multiple chat-model candidates in one go and
# print a side-by-side comparison. Each model is loaded fresh (others
# unloaded first) to ensure VRAM contention doesn't skew results.
#
# Run after 9070 XT install to decide MB's primary chat model.
#
# Default candidate set is the pre-pulled list as of 2026-05-19:
#   qwen2.5:14b  - fleet's existing standard
#   qwen3:14b    - direct successor, fleet-family consistent
#   phi4:14b     - Microsoft, strong reasoning/math/code
#
# Usage:
#   .\Bench-All.ps1
#   .\Bench-All.ps1 -Models @('qwen3:14b','phi4:14b','mistral-small:24b')

[CmdletBinding()]
param(
    [string[]]$Models = @('qwen2.5:14b', 'qwen3:14b', 'phi4:14b'),
    [int]$ChatTokens = 200,
    [string]$Note = 'Bench-All comparison'
)

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'
$ScriptDir = $PSScriptRoot

function Write-Status($msg, $color = 'Cyan') { Write-Host "[Bench-All] $msg" -ForegroundColor $color }

# Pre-flight: confirm all candidates are pulled
Write-Status "Pre-flight: confirming candidates are pulled ..."
$tags = (Invoke-RestMethod -Uri "$OLLAMA/api/tags" -TimeoutSec 5).models
$missing = @()
foreach ($m in $Models) {
    if (-not ($tags | Where-Object { $_.name -like "$m*" })) {
        $missing += $m
        Write-Host "  MISSING: $m" -ForegroundColor Red
    } else {
        Write-Host "  ok:      $m" -ForegroundColor Green
    }
}
if ($missing.Count -gt 0) {
    Write-Status "Pull missing models first: $($missing -join ', ')" 'Red'
    Write-Status "  ollama pull $($missing -join '; ollama pull ')" 'Yellow'
    exit 1
}

# Bench each model
$results = @()
foreach ($model in $Models) {
    Write-Status ""
    Write-Status "=== Bench: $model ===" 'Yellow'

    # Unload everything else so VRAM is uncontended
    $ps = (Invoke-RestMethod -Uri "$OLLAMA/api/ps").models
    foreach ($loaded in $ps) {
        if ($loaded.name -ne $model) {
            $unload = @{ model = $loaded.name; keep_alive = 0 } | ConvertTo-Json -Compress
            try { Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $unload -ContentType 'application/json' -TimeoutSec 10 | Out-Null } catch {}
        }
    }
    Start-Sleep -Seconds 2

    # Warmup
    $warm = @{ model = $model; prompt = 'hi'; stream = $false; keep_alive = '5m'; options = @{ num_predict = 1 } } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $warm -ContentType 'application/json' -TimeoutSec 180 | Out-Null
    } catch {
        Write-Status "Warmup failed for $model : $($_.Exception.Message)" 'Red'
        $results += [pscustomobject]@{ model = $model; tok_per_sec = 0; vram_mb = 0; status = 'WARMUP_FAILED' }
        continue
    }

    # Capture VRAM footprint
    $loaded = (Invoke-RestMethod -Uri "$OLLAMA/api/ps").models | Where-Object { $_.name -like "$model*" } | Select-Object -First 1
    $vramMB = if ($loaded -and $loaded.size_vram) { [math]::Round($loaded.size_vram / 1MB, 0) } else { 0 }
    $totalMB = if ($loaded -and $loaded.size) { [math]::Round($loaded.size / 1MB, 0) } else { 0 }
    $pctGpu = if ($totalMB -gt 0) { [math]::Round(($vramMB / $totalMB) * 100, 0) } else { 0 }

    # Bench
    $body = @{
        model      = $model
        prompt     = 'Write a detailed essay about the history of computer architecture, covering early vacuum tubes through modern multi-core processors.'
        stream     = $false
        keep_alive = '5m'
        options    = @{ num_predict = $ChatTokens }
    } | ConvertTo-Json -Compress
    try {
        $r = Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 600
        $tokSec = [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 2)
        Write-Host ("  {0,-20} {1,8:N2} tok/sec  VRAM {2} MB ({3}% GPU)" -f $model, $tokSec, $vramMB, $pctGpu) -ForegroundColor Green
        $results += [pscustomobject]@{ model = $model; tok_per_sec = $tokSec; vram_mb = $vramMB; pct_gpu = $pctGpu; status = 'OK' }

        # Append to main CSV
        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
        $gpuName = (Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Radeon|GeForce|RX|RTX' } | Select-Object -First 1).Name
        $envExtra = & nssm get OllamaService AppEnvironmentExtra 2>$null
        $backend = if ($envExtra -match 'OLLAMA_VULKAN=1') { 'Vulkan' } elseif ($envExtra -match 'ROCBLAS_TENSILE_LIBPATH') { 'ROCm' } else { 'unknown' }
        $version = (Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 5).version
        $row = "$timestamp,`"$gpuName`",$backend,$version,$model,$tokSec,,,`"$Note`""
        Add-Content -Path (Join-Path $ScriptDir 'benchmarks.csv') -Value $row -Encoding UTF8
    } catch {
        Write-Status "Bench failed for $model : $($_.Exception.Message)" 'Red'
        $results += [pscustomobject]@{ model = $model; tok_per_sec = 0; vram_mb = $vramMB; status = 'BENCH_FAILED' }
    }
}

# Comparison table
Write-Host ""
Write-Host "=================== Comparison ===================" -ForegroundColor Yellow
$results | Sort-Object -Property tok_per_sec -Descending | Format-Table model, tok_per_sec, vram_mb, pct_gpu, status -AutoSize

$winner = $results | Where-Object { $_.status -eq 'OK' } | Sort-Object -Property tok_per_sec -Descending | Select-Object -First 1
if ($winner) {
    Write-Host "Speed winner: $($winner.model) at $($winner.tok_per_sec) tok/sec" -ForegroundColor Green
    Write-Host ""
    Write-Host "Speed is only half the picture - test each model qualitatively on a real prompt you care about" -ForegroundColor Cyan
    Write-Host "(NPC-PM coach review, log triage, RAG synthesis, whatever) before committing to AI-Resume.ps1." -ForegroundColor Cyan
}

exit 0
