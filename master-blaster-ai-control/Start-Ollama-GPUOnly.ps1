# Start-Ollama-GPUOnly.ps1 - NSSM-friendly wrapper around `ollama serve` that
# enforces "GPU or nothing" on the RX 9070 XT. If Ollama starts but its GPU
# discovery fails (ROCm/HIP wedged - the ollama#13920 family), the wrapper
# kills the child process and exits non-zero so NSSM won't keep it running.
#
# Background: built 2026-05-20 after BG3's keep_alive=0 ingestion loop
# thrashed the ROCm context until GPU discovery silently returned zero
# devices and Ollama loaded qwen3:14b entirely into 32 GB system RAM.
# Setting OLLAMA_LLM_LIBRARY=rocm is not honored as a hard gate in
# Ollama 0.21.2 - this wrapper is the real enforcement.
#
# Detection: parses NSSM service stderr for the `inference compute` lines
# emitted once per backend at boot. A healthy MB boot has at least one
# `library=ROCm` (or cuda/vulkan); a wedged boot has only `library=cpu`.
#
# NSSM config to use this:
#   AppExecutable     C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
#   AppParameters     -NoProfile -ExecutionPolicy Bypass -File "C:\falkensteink\AIInfrastructure\master-blaster-ai-control\Start-Ollama-GPUOnly.ps1"
#   AppDirectory      C:\falkensteink\AIInfrastructure\master-blaster-ai-control
#   AppEnvironmentExtra (unchanged - all OLLAMA_* + ROCBLAS_TENSILE_LIBPATH stay)
#
# Exit codes (NSSM logs these in service-exit-codes):
#   0  - ollama serve exited normally (NSSM's stop signal)
#   non-zero - ollama serve's own exit code, OR:
#   11 - serve didn't respond on /api/version within the boot window
#   12 - serve responded but only library=cpu was discovered (GPU failed)

$ErrorActionPreference = 'Stop'

# --- Tunables --------------------------------------------------------------
$OllamaExe       = 'C:\Users\kylej\AppData\Local\Programs\Ollama\ollama.exe'
$StderrLog       = 'C:\Users\kylej\ollama-logs\service-stderr.log'
$ApiBase         = 'http://localhost:11434'
$BootTimeoutSec  = 45      # qwen3:14b warm-set + ROCm init can take a moment
# ---------------------------------------------------------------------------

function Write-WrapLog($msg) {
    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    Write-Host "[gpu-only-wrapper $ts] $msg"
}

# Mark the stderr log's current size BEFORE spawning ollama so we read ONLY
# this boot's output. Critical to avoid false-positive GPU detection from a
# previous good boot's `inference compute` lines leaking into our scan.
$logSizeAtStart = if (Test-Path $StderrLog) { (Get-Item $StderrLog).Length } else { 0 }
Write-WrapLog "stderr log size at start: $logSizeAtStart bytes - will only scan new bytes after this"

# Spawn `ollama serve` as a child we can supervise.
Write-WrapLog "spawning: $OllamaExe serve"
$proc = Start-Process -FilePath $OllamaExe -ArgumentList 'serve' -PassThru -NoNewWindow

# Wrap the supervision in try/finally so an unexpected wrapper exit doesn't
# leave ollama.exe orphaned. NSSM-initiated stop will land in the WaitForExit.
try {
    # --- Phase 1: wait for the HTTP listener -------------------------------
    Write-WrapLog "waiting up to ${BootTimeoutSec}s for /api/version ..."
    $deadline = (Get-Date).AddSeconds($BootTimeoutSec)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            Write-WrapLog "ollama.exe exited during boot with code $($proc.ExitCode)"
            exit ($proc.ExitCode)
        }
        try {
            Invoke-RestMethod -Uri "$ApiBase/api/version" -TimeoutSec 2 -ErrorAction Stop | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        Write-WrapLog "TIMEOUT: ollama did not respond on /api/version within ${BootTimeoutSec}s"
        exit 11
    }
    Write-WrapLog "ollama responsive; verifying GPU discovery"

    # --- Phase 2: verify GPU was enumerated --------------------------------
    # Give ollama a moment to finish writing its boot summary to stderr.
    Start-Sleep -Seconds 1

    if (-not (Test-Path $StderrLog)) {
        Write-WrapLog "FAIL: stderr log not at $StderrLog - cannot verify GPU discovery"
        exit 12
    }
    # Read ONLY the bytes appended since wrapper start - any compute lines we
    # see come from THIS boot, not a previous one with different GPU state.
    $newBytes = $null
    try {
        $fs = [System.IO.File]::Open($StderrLog, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            if ($fs.Length -gt $logSizeAtStart) {
                $fs.Seek($logSizeAtStart, [System.IO.SeekOrigin]::Begin) | Out-Null
                $reader = New-Object System.IO.StreamReader($fs)
                $newBytes = $reader.ReadToEnd()
            } else {
                # Log may have been rotated/truncated. Fall back to whole file.
                Write-WrapLog "stderr log shrank ($($fs.Length) < $logSizeAtStart) - probably rotated; reading entire file"
                $fs.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null
                $reader = New-Object System.IO.StreamReader($fs)
                $newBytes = $reader.ReadToEnd()
            }
        } finally { $fs.Dispose() }
    } catch {
        Write-WrapLog "FAIL: could not read stderr log: $($_.Exception.Message)"
        exit 12
    }
    $thisBootLines = $newBytes -split "`r?`n"
    $computeLines = $thisBootLines | Where-Object { $_ -match 'inference compute' }

    if (-not $computeLines) {
        Write-WrapLog "FAIL: no 'inference compute' lines in this boot's stderr ($(($thisBootLines | Measure-Object).Count) lines total)"
        Write-WrapLog "last 10 lines from this boot for diagnosis:"
        $thisBootLines | Where-Object { $_ } | Select-Object -Last 10 | ForEach-Object { Write-WrapLog "  | $_" }
        exit 12
    }

    $gpuBackends = @()
    $cpuSeen     = $false
    foreach ($line in $computeLines) {
        if ($line -match 'library=(ROCm|cuda|vulkan)') { $gpuBackends += $matches[1] }
        elseif ($line -match 'library=cpu')             { $cpuSeen = $true }
    }
    $gpuBackends = $gpuBackends | Sort-Object -Unique

    if ($gpuBackends.Count -eq 0) {
        Write-WrapLog "FAIL: GPU not discovered (cpu seen: $cpuSeen, compute lines: $($computeLines.Count))"
        Write-WrapLog "compute lines from this boot:"
        foreach ($line in $computeLines) { Write-WrapLog "  | $line" }
        exit 12
    }

    Write-WrapLog "PASS: GPU discovered, backend(s): $($gpuBackends -join ', '). supervising ollama..."

    # --- Phase 3: supervise child until it exits ---------------------------
    # When NSSM stops the service it kills powershell.exe; the finally block
    # below cleans up the orphaned ollama.exe. Otherwise we block here for
    # the lifetime of the serve.
    $proc.WaitForExit()
    Write-WrapLog "ollama serve exited with code $($proc.ExitCode)"
    exit $proc.ExitCode
} finally {
    if ($proc -and -not $proc.HasExited) {
        Write-WrapLog "wrapper exiting; force-stopping ollama.exe PID $($proc.Id)"
        try { Stop-Process -Id $proc.Id -Force -ErrorAction Stop } catch {
            Write-WrapLog "  Stop-Process failed: $($_.Exception.Message)"
        }
    }
}
