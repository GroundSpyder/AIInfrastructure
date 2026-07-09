# Install-9070XT-ROCm.ps1 - automate the Ollama-on-ROCm migration for MB's
# RX 9070 XT install. Run this AFTER:
#   1. Physical card installed
#   2. AMD Adrenalin (latest, RDNA 4 support) installed and rebooted
#   3. AMD HIP SDK 7.1.1+ installed to C:\Program Files\AMD\ROCm\7.1\
#
# What this script does:
#   - Sanity-checks the HIP SDK install (gfx120x rocBLAS libraries present)
#   - Updates OllamaService NSSM env vars (drops Vulkan flags, adds ROCBLAS path)
#   - Restarts the service
#   - Runs Verify-GPU.ps1 to confirm ROCm is actually working
#   - Runs Bench.ps1 to capture post-install numbers
#
# If verify fails: prints the rollback command and exits non-zero.

[CmdletBinding()]
param(
    [string]$HipSdkPath = 'C:\Program Files\AMD\ROCm\7.1',
    [switch]$Force  # skip "are you sure" prompt
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
function Write-Status($msg, $color = 'Cyan') { Write-Host "[Install] $msg" -ForegroundColor $color }

# --- Phase 1: Sanity checks ---
Write-Status "Phase 1: HIP SDK sanity checks"

if (-not (Test-Path $HipSdkPath)) {
    Write-Status "HIP SDK not found at $HipSdkPath" 'Red'
    Write-Status "Download AMD HIP SDK 7.1.1+ from:" 'Yellow'
    Write-Status "  https://rocm.docs.amd.com/projects/install-on-windows/en/latest/reference/system-requirements.html" 'Yellow'
    exit 1
}

$rocBlasLib = Join-Path $HipSdkPath 'bin\rocblas\library'
if (-not (Test-Path $rocBlasLib)) {
    Write-Status "rocBLAS library dir missing: $rocBlasLib" 'Red'
    exit 1
}

$gfx120Files = Get-ChildItem -Path $rocBlasLib -Filter '*gfx120*' -ErrorAction SilentlyContinue
if ($gfx120Files.Count -eq 0) {
    Write-Status "No gfx120x libraries found in $rocBlasLib - HIP SDK may be too old." 'Red'
    Write-Status "Need HIP SDK 7.1.1+ (the version with RX 9000 series support)." 'Yellow'
    exit 1
}
Write-Status "Found $($gfx120Files.Count) gfx120x rocBLAS files. Good." 'Green'

# --- Phase 2: Confirm with user ---
if (-not $Force) {
    Write-Host ""
    Write-Status "About to update OllamaService:" 'Yellow'
    Write-Host "  REMOVE: OLLAMA_VULKAN=1, OLLAMA_LLM_LIBRARY=vulkan"
    Write-Host "  ADD   : ROCBLAS_TENSILE_LIBPATH=$rocBlasLib"
    Write-Host "  KEEP  : OLLAMA_HOST, OLLAMA_MAX_LOADED_MODELS, OLLAMA_NUM_PARALLEL, OLLAMA_KEEP_ALIVE, OLLAMA_MODELS"
    Write-Host ""
    $reply = Read-Host "Proceed? (y/N)"
    if ($reply -notmatch '^y') { Write-Status "Aborted." 'Yellow'; exit 0 }
}

# --- Phase 3: Apply NSSM config ---
Write-Status "Phase 3: Applying NSSM env-var changes"

# NSSM AppEnvironmentExtra takes each KEY=VAL as a separate positional arg.
# Joining them into a single string silently corrupts the env block -
# documented Kaydanski landmine, see root CLAUDE.md 2026-04-24 entry.
$envVars = @(
    "OLLAMA_HOST=0.0.0.0:11434"
    "OLLAMA_MAX_LOADED_MODELS=2"
    "OLLAMA_NUM_PARALLEL=2"
    "OLLAMA_KEEP_ALIVE=30m"
    "OLLAMA_MODELS=C:\Users\kylej\.ollama\models"
    "ROCBLAS_TENSILE_LIBPATH=$rocBlasLib"
)

& nssm set OllamaService AppEnvironmentExtra $envVars
if ($LASTEXITCODE -ne 0) { Write-Status "nssm set failed (exit $LASTEXITCODE)" 'Red'; exit 2 }

& nssm set OllamaService Description "Local Ollama on RX 9070 XT (ROCm backend via HIP SDK 7.1+). Pause/resume via Ctrl+Alt+P / Ctrl+Alt+R."
Write-Status "NSSM updated. Restarting service ..." 'Green'

& nssm restart OllamaService
Start-Sleep -Seconds 5

# Wait for API to come back
$deadline = (Get-Date).AddSeconds(30)
$apiUp = $false
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-RestMethod -Uri 'http://localhost:11434/api/version' -TimeoutSec 3 | Out-Null
        $apiUp = $true
        break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $apiUp) {
    Write-Status "Ollama API didn't come back after 30s. Check service logs." 'Red'
    Write-Status "Rollback: nssm set OllamaService AppEnvironmentExtra OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_NUM_PARALLEL=2 OLLAMA_KEEP_ALIVE=30m OLLAMA_MODELS=C:\Users\kylej\.ollama\models OLLAMA_VULKAN=1 OLLAMA_LLM_LIBRARY=vulkan && nssm restart OllamaService" 'Yellow'
    exit 3
}
Write-Status "API back up." 'Green'

# --- Phase 4: Warm models ---
Write-Status "Phase 4: Warming default models (uses 9070 XT VRAM)"
& "$ScriptDir\AI-Resume.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Status "AI-Resume.ps1 returned non-zero. Check above for details." 'Red'
    exit 4
}

# --- Phase 5: Verify GPU usage (catches #13920) ---
Write-Status "Phase 5: Verifying GPU is actually in use"
& "$ScriptDir\Verify-GPU.ps1"
$verifyExit = $LASTEXITCODE
if ($verifyExit -ne 0) {
    Write-Status "Verify-GPU returned $verifyExit - silent CPU fallback likely (ollama#13920)." 'Red'
    Write-Status "Try the Vulkan fallback:" 'Yellow'
    Write-Host '  nssm set OllamaService AppEnvironmentExtra OLLAMA_HOST=0.0.0.0:11434 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_NUM_PARALLEL=2 OLLAMA_KEEP_ALIVE=30m OLLAMA_MODELS=C:\Users\kylej\.ollama\models OLLAMA_VULKAN=1 OLLAMA_LLM_LIBRARY=vulkan'
    Write-Host '  nssm restart OllamaService'
    exit 5
}

# --- Phase 6: Bench against the new warm-set chat model ---
# Default to 14b - 16 GB VRAM makes that the right size class. Fall back to
# 7b if 14b isn't pulled yet.
$benchModel = 'qwen2.5:14b'
$tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
if (-not ($tags.models | Where-Object { $_.name -like 'qwen2.5:14b*' })) {
    Write-Status "qwen2.5:14b not pulled, falling back to 7b for bench" 'Yellow'
    $benchModel = 'qwen2.5:7b'
}

Write-Status "Phase 6: Benchmark - comparing to pre-install baseline ($benchModel)"
& "$ScriptDir\Bench.ps1" -ChatModel $benchModel -Note "post 9070 XT ROCm $benchModel"
Write-Status "Check benchmarks.csv for before/after comparison." 'Green'

Write-Host ""
Write-Status "Final step: edit AI-Resume.ps1 to use the post-9070XT warm set" 'Yellow'
Write-Status "  (uncomment the `$CHAT_MODELS = @('qwen2.5:14b') block)" 'Yellow'

Write-Status "Migration complete." 'Green'
exit 0
