<#
.SYNOPSIS
  Install whisper.cpp as a Windows service on Master Blaster, as Snoop's
  secondary transcription backend.

.DESCRIPTION
  Master Blaster is the SECONDARY whisper backend. Kaydanski is primary because
  it runs 24/7; MB is faster but is Kyle's dev and gaming box. Without a
  secondary, the worker warns on every start:

    "WHISPER_SECONDARY_URL is not set, so there is no fallback backend. Every
     gaming session on Kaydanski will stall the queue until it ends."

  This script must run ELEVATED. Everything in it needs admin:
    - the inbound firewall rule (Kaydanski cannot reach :8035 without it)
    - the NSSM service registration
    - the optional Vulkan toolchain install

  Run it as:   gsudo -- powershell -ExecutionPolicy Bypass -File .\Install-WhisperServer.ps1
  or from an Administrator PowerShell directly.

  -WithGpuBuild also installs cmake + the Vulkan SDK + VS Build Tools and
  compiles whisper.cpp with GGML_VULKAN=ON. Without it the CPU build is used,
  which on this box measures 3.88x SLOWER than realtime for large-v3 - fine as
  a queue-draining fallback, poor as anything else.

.NOTES
  Ports and layout match Kaydanski deliberately: 0.0.0.0:8035, service name
  WhisperCppServer, so the two hosts are interchangeable to the worker.
#>
[CmdletBinding()]
param(
    [switch]$WithGpuBuild,
    [int]$Port = 8035,
    [string]$Root = "C:\whisper",
    [string]$ServiceName = "WhisperCppServer"
)

$ErrorActionPreference = "Stop"

function Assert-Elevated {
    $isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This script must run elevated. Re-run via: gsudo -- powershell -ExecutionPolicy Bypass -File $PSCommandPath"
    }
}

function Find-Nssm {
    $c = Get-Command nssm -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "nssm.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    throw "nssm.exe not found. Install with: winget install NSSM.NSSM"
}

Assert-Elevated
Write-Host "== whisper.cpp server install on $env:COMPUTERNAME ==" -ForegroundColor Cyan

# ---------------------------------------------------------------- model check
$model = Join-Path $Root "models\ggml-large-v3.bin"
if (-not (Test-Path $model)) {
    throw "Model missing at $model. Fetch it first (ungated, no token needed):`n" +
          "  curl.exe -L -o `"$model`" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
}
Write-Host ("model: {0:N0} MB" -f ((Get-Item $model).Length / 1MB))

# ------------------------------------------------------------ optional GPU build
$exe = Join-Path $Root "prebuilt\Release\whisper-server.exe"

if ($WithGpuBuild) {
    Write-Host "-- installing build toolchain (this is several GB) --" -ForegroundColor Yellow
    # Serially, NOT in parallel: two MSI/VS installers at once fail with
    # 1618 "Another installation is already in progress".
    winget install --id Kitware.CMake --exact --silent --accept-package-agreements --accept-source-agreements
    winget install --id KhronosGroup.VulkanSDK --exact --silent --accept-package-agreements --accept-source-agreements
    winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --silent `
        --accept-package-agreements --accept-source-agreements `
        --override "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64"

    $src = Join-Path $Root "whisper.cpp"
    if (-not (Test-Path $src)) {
        git clone --depth 1 --branch v1.9.2 https://github.com/ggml-org/whisper.cpp $src
    }
    $cmake = "C:\Program Files\CMake\bin\cmake.exe"
    if (-not (Test-Path $cmake)) { throw "cmake still not present after install" }

    Push-Location $src
    try {
        & $cmake -B build -DGGML_VULKAN=ON -DWHISPER_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
        & $cmake --build build --config Release -j
    } finally { Pop-Location }

    $built = Join-Path $src "build\bin\Release\whisper-server.exe"
    if (Test-Path $built) {
        $exe = $built
        Write-Host "using GPU build: $exe" -ForegroundColor Green
    } else {
        Write-Warning "GPU build produced no whisper-server.exe; falling back to the CPU build."
    }
}

if (-not (Test-Path $exe)) { throw "whisper-server.exe not found at $exe" }

# ------------------------------------------------------------------- firewall
# Kaydanski's worker reaches this over the LAN/tailnet. Without this rule the
# port listens on 0.0.0.0 and is still silently unreachable - and per
# MASTERBLASTER.md, a blocked Windows port DROPS packets rather than refusing,
# so the caller hangs to its own timeout instead of failing fast.
$ruleName = "Snoop whisper.cpp server ($Port)"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private, Domain | Out-Null
Write-Host "firewall: inbound TCP $Port allowed (Private/Domain only - NOT Public)"

# -------------------------------------------------------------------- service
$nssm = Find-Nssm
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "stopping existing $ServiceName"
    & $nssm stop $ServiceName | Out-Null
    & $nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
}

& $nssm install $ServiceName $exe | Out-Null
& $nssm set $ServiceName AppParameters "-m `"$model`" --host 0.0.0.0 --port $Port -t 8" | Out-Null
& $nssm set $ServiceName DisplayName "Whisper.cpp Server (Snoop secondary backend)" | Out-Null
& $nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $nssm set $ServiceName AppStdout "$Root\server.log" | Out-Null
& $nssm set $ServiceName AppStderr "$Root\server.err.log" | Out-Null
& $nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $nssm start $ServiceName | Out-Null

Start-Sleep -Seconds 15
$svc = Get-Service $ServiceName
Write-Host "service $ServiceName -> $($svc.Status)" -ForegroundColor Green

# ----------------------------------------------------------------- verify
# Verify by exercising it, not by reading the service state. Per the 2026-05-19
# ROCm migration: /api/ps and a Running service both lied about GPU use once;
# only a real request settles it.
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 20
    Write-Host "local HTTP: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Warning "local HTTP probe failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "NEXT: point the Snoop worker at this host." -ForegroundColor Cyan
Write-Host "  On Kaydanski, in C:\snoop-worker-deploy\.env add:"
Write-Host "    WHISPER_SECONDARY_URL=http://192.168.4.33:$Port"
Write-Host "  then:  schtasks /Run /TN SnoopWorkerComposeUp"
Write-Host ""
Write-Host "CONSIDER: add this service to the gaming gate (Game-Watch.ps1) if GPU-built," -ForegroundColor Yellow
Write-Host "  so it yields the GPU during games the way OllamaService already does."
