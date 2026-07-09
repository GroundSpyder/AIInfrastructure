# Bench.ps1 - reusable benchmark for MB Ollama. Appends a row to benchmarks.csv.
# Use it before/after GPU swap, before/after Ollama upgrade, etc. - single
# command, comparable numbers.
#
# Usage:
#   .\Bench.ps1                              # uses default models, auto-detects GPU/backend
#   .\Bench.ps1 -ChatModel qwen2.5:7b       # override
#   .\Bench.ps1 -Note "post 9070XT ROCm"    # tags the row

[CmdletBinding()]
param(
    [string]$ChatModel = 'qwen2.5:3b',
    [string]$EmbedModel = 'bge-m3:latest',
    [int]$ChatTokens = 200,
    [int]$EmbedBatchSize = 10,
    [string]$Note = ''
)

$ErrorActionPreference = 'Stop'
$OLLAMA = 'http://localhost:11434'
$CsvPath = Join-Path $PSScriptRoot 'benchmarks.csv'

function Write-Status($msg, $color = 'Cyan') { Write-Host "[Bench] $msg" -ForegroundColor $color }

# Auto-detect environment
try {
    $version = (Invoke-RestMethod -Uri "$OLLAMA/api/version" -TimeoutSec 5).version
} catch {
    Write-Status "Ollama API not responding at $OLLAMA" 'Red'
    exit 1
}

# Heuristic backend detection from NSSM env vars
$backend = 'unknown'
$envExtra = & nssm get OllamaService AppEnvironmentExtra 2>$null
if ($envExtra -match 'OLLAMA_VULKAN=1') { $backend = 'Vulkan' }
elseif ($envExtra -match 'ROCBLAS_TENSILE_LIBPATH') { $backend = 'ROCm' }
elseif ($envExtra -match 'CUDA') { $backend = 'CUDA' }

# Best-effort GPU detection via WMI (give us "RX 580" / "RX 9070 XT" string)
$gpuName = (Get-CimInstance -ClassName Win32_VideoController -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'Radeon|GeForce|RX|RTX' } |
            Select-Object -First 1).Name
if (-not $gpuName) { $gpuName = 'unknown' }

Write-Status "Env  : Ollama $version | $gpuName | $backend"
Write-Status "Bench: chat=$ChatModel ($ChatTokens tok) embed=$EmbedModel (batch $EmbedBatchSize)"

# --- Warmup: ensure both models are in VRAM so load-time doesn't pollute timings ---
Write-Status "Warming models (excluded from timing) ..."
try {
    $warmChat = @{ model = $ChatModel; prompt = 'hi'; stream = $false; keep_alive = '5m'; options = @{ num_predict = 1 } } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $warmChat -ContentType 'application/json' -TimeoutSec 120 | Out-Null
} catch { Write-Status "Chat warmup failed: $($_.Exception.Message)" 'Red'; exit 2 }
try {
    $warmEmbed = @{ model = $EmbedModel; input = 'warmup'; keep_alive = '5m' } | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$OLLAMA/api/embed" -Method Post -Body $warmEmbed -ContentType 'application/json' -TimeoutSec 120 | Out-Null
} catch { Write-Status "Embed warmup failed: $($_.Exception.Message)" 'Red'; exit 3 }

# --- Chat benchmark ---
Write-Status "Running chat benchmark ..."
$chatBody = @{
    model      = $ChatModel
    prompt     = 'Write a detailed essay about the history of computer architecture.'
    stream     = $false
    keep_alive = '5m'
    options    = @{ num_predict = $ChatTokens }
} | ConvertTo-Json -Compress
try {
    $r = Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post -Body $chatBody `
        -ContentType 'application/json' -TimeoutSec 600
    $tokSec = [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 2)
    Write-Host ("  {0} -> {1} tok/sec ({2} tok in {3:N2}s)" -f $ChatModel, $tokSec, $r.eval_count, ($r.eval_duration/1e9)) -ForegroundColor Green
} catch {
    Write-Status "Chat benchmark FAILED: $($_.Exception.Message)" 'Red'
    exit 2
}

# --- Embed benchmark ---
Write-Status "Running embed benchmark ..."
$texts = 1..$EmbedBatchSize | ForEach-Object { "Sample text number $_ for benchmarking embeddings on Master Blaster." }
$embedBody = @{
    model      = $EmbedModel
    input      = $texts
    keep_alive = '5m'
} | ConvertTo-Json -Compress
try {
    $sw = [diagnostics.stopwatch]::StartNew()
    Invoke-RestMethod -Uri "$OLLAMA/api/embed" -Method Post -Body $embedBody `
        -ContentType 'application/json' -TimeoutSec 300 | Out-Null
    $sw.Stop()
    $embedSec = [math]::Round($EmbedBatchSize / $sw.Elapsed.TotalSeconds, 2)
    Write-Host ("  {0} -> {1} embed/sec ({2} inputs in {3}ms)" -f $EmbedModel, $embedSec, $EmbedBatchSize, [math]::Round($sw.Elapsed.TotalMilliseconds, 0)) -ForegroundColor Green
} catch {
    Write-Status "Embed benchmark FAILED: $($_.Exception.Message)" 'Red'
    exit 3
}

# --- Append to CSV ---
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
$row = "$timestamp,`"$gpuName`",$backend,$version,$ChatModel,$tokSec,$EmbedModel,$embedSec,`"$Note`""
Add-Content -Path $CsvPath -Value $row -Encoding UTF8
Write-Status "Appended to $CsvPath" 'Green'

Write-Host ""
Write-Host "=== Bench Summary ===" -ForegroundColor Yellow
Write-Host "  GPU         : $gpuName"
Write-Host "  Backend     : $backend"
Write-Host "  Chat ($ChatModel) : $tokSec tok/sec"
Write-Host "  Embed ($EmbedModel) : $embedSec embed/sec"
if ($Note) { Write-Host "  Note        : $Note" }
exit 0
