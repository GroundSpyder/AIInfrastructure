# Verify-GPU.ps1 - confirm Ollama is actually using the GPU, not silently
# falling back to CPU. Built specifically to catch ollama#13920 - the
# "filtering device which didn't fully initialize" landmine on RX 9070 XT
# where /api/ps reports a model but inference quietly runs on CPU.
#
# Exit codes:
#   0 = GPU-backed inference confirmed
#   1 = Ollama API not reachable
#   2 = No models loaded (run AI-Resume first)
#   3 = Loaded but size_vram = 0 (likely CPU fallback)
#   4 = Loaded with VRAM but token rate below CPU threshold (definite fallback)
#   5 = Service logs show known-bad signatures (#13920)

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'
$LOG_STDERR = 'C:\Users\kylej\ollama-logs\service-stderr.log'

# Tunable: a 9070 XT on ROCm should comfortably exceed this; CPU on this box
# was ~8-16 tok/sec for qwen2.5:7b per ollama#12573 reports. 20 tok/sec is the
# floor - anything below means we're not really on GPU.
$MIN_TOK_PER_SEC = 20

function Write-Status($msg, $color = 'Cyan') { Write-Host "[Verify-GPU] $msg" -ForegroundColor $color }

# 1. API reachability
Write-Status "Querying $OLLAMA ..."
try {
    $version = (Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 5).version
    Write-Host "  Ollama version: $version"
} catch {
    Write-Status "FAILED: Ollama API not responding" 'Red'
    exit 1
}

# 2. Loaded models + VRAM check
$ps = Invoke-RestMethod -Uri "$OLLAMA/api/ps" -TimeoutSec 5
if (-not $ps.models -or $ps.models.Count -eq 0) {
    Write-Status "No models loaded. Run AI-Resume.ps1 first." 'Yellow'
    exit 2
}

Write-Status "Loaded models:"
$cpuOnly = @()
foreach ($m in $ps.models) {
    if ($null -eq $m.PSObject.Properties['size_vram']) {
        Write-Host ("  - {0}  (no size_vram field - API drift?)" -f $m.name) -ForegroundColor Yellow
        continue
    }
    $vramMB = [math]::Round($m.size_vram / 1MB, 0)
    $totalMB = [math]::Round($m.size / 1MB, 0)
    $pctGpu = if ($totalMB -gt 0) { [math]::Round(($vramMB / $totalMB) * 100, 0) } else { 0 }

    if ($vramMB -eq 0) {
        Write-Host ("  - {0}  ON CPU (size_vram=0, size={1} MB)" -f $m.name, $totalMB) -ForegroundColor Red
        $cpuOnly += $m.name
    } elseif ($pctGpu -lt 90) {
        Write-Host ("  - {0}  PARTIAL: {1} MB / {2} MB on GPU ({3}%)" -f $m.name, $vramMB, $totalMB, $pctGpu) -ForegroundColor Yellow
    } else {
        Write-Host ("  - {0}  GPU: {1} MB / {2} MB ({3}%)" -f $m.name, $vramMB, $totalMB, $pctGpu) -ForegroundColor Green
    }
}

if ($cpuOnly.Count -gt 0) {
    Write-Status "CPU-only models detected. Likely ROCm init failure (ollama#13920) or library mismatch." 'Red'
    Write-Status "Check $LOG_STDERR for 'filtering device' or 'CPU mode' messages." 'Yellow'
    exit 3
}

# 3. Token-rate sanity check - catch fallbacks that report fake VRAM numbers
$chatModel = ($ps.models | Where-Object { $_.details.family -notmatch 'bert' } | Select-Object -First 1).name
if ($chatModel) {
    Write-Status "Inference speed test: $chatModel (50 tok generation)"
    $body = @{
        model      = $chatModel
        prompt     = 'Count from one to twenty in plain words, one per line.'
        stream     = $false
        keep_alive = '5m'
        options    = @{ num_predict = 50 }
    } | ConvertTo-Json -Compress
    try {
        $r = Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 120
        $tokSec = [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 2)
        if ($tokSec -ge $MIN_TOK_PER_SEC) {
            Write-Host ("  {0} tok/sec - GPU OK" -f $tokSec) -ForegroundColor Green
        } else {
            Write-Host ("  {0} tok/sec - BELOW CPU FLOOR ({1}). Almost certainly silent CPU fallback." -f $tokSec, $MIN_TOK_PER_SEC) -ForegroundColor Red
            exit 4
        }
    } catch {
        Write-Status "Speed test failed: $($_.Exception.Message)" 'Red'
        exit 4
    }
}

# 4. Service-log scan for known-bad signatures
if (Test-Path $LOG_STDERR) {
    $recentLog = Get-Content $LOG_STDERR -Tail 200 -ErrorAction SilentlyContinue
    $hits = @()
    foreach ($line in $recentLog) {
        if ($line -match 'filtering device which didn.?t fully initialize') { $hits += "ollama#13920 (filtering device): $line" }
        if ($line -match 'low.?vram mode') { $hits += "low-vram mode: $line" }
        if ($line -match 'falling back to CPU') { $hits += "CPU fallback declared: $line" }
    }
    if ($hits.Count -gt 0) {
        Write-Status "Service log contains known-bad signatures:" 'Red'
        $hits | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        exit 5
    }
}

Write-Status "All checks passed. GPU inference confirmed." 'Green'
exit 0
