<#
.SYNOPSIS
  Install whisper.cpp as a Windows service on Master Blaster, as Snoop's
  secondary transcription backend. GPU via ROCm.

.DESCRIPTION
  Master Blaster is the SECONDARY whisper backend. Kaydanski is primary because it
  runs 24/7; MB is faster but is Kyle's dev and gaming box. Without a secondary the
  worker warns on every start that every gaming session on Kaydanski stalls the queue.

  **Use ROCm, not Vulkan.** Measured 2026-08-07 on this exact card:

    CPU (prebuilt BLAS)        3.88x SLOWER than realtime
    Vulkan (MinGW and MSVC)    builds, detects the GPU, then crashes 0xC0000005
    ROCm/HIP gfx1201           0.11x realtime warm  <-- what this script builds

  The Vulkan crash reproduces across two compilers and two whisper.cpp versions while
  the same binaries transcribe fine on CPU, so it is ggml's Vulkan backend on RDNA 4
  plus AMD's proprietary Windows driver. ROCm is the backend Ollama already uses on
  this host. Details in MASTERBLASTER.md.

  Must run ELEVATED - the firewall rule and NSSM registration both need admin:

    gsudo -- powershell -ExecutionPolicy Bypass -File .\Install-WhisperServer.ps1

  -SkipBuild reuses an existing build (fast re-registration of the service).

.NOTES
  Port and service name match Kaydanski deliberately, so the two hosts are
  interchangeable to the Snoop worker.

  VERIFY FROM KAYDANSKI, NEVER FROM HERE. Two things silently break remote reach while
  every local check stays green: Tailscale sits in NoState after a reboot until the GUI
  client runs, and the firewall rule has been observed not surviving a reboot.
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [int]$Port = 8035,
    [string]$Root = "C:\whisper",
    [string]$ServiceName = "WhisperCppServer",
    [string]$RocmPath = "C:\Program Files\AMD\ROCm\6.4",
    [string]$GpuTarget = "gfx1201"
)

$ErrorActionPreference = "Stop"

function Assert-Elevated {
    $isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "Must run elevated. Re-run via: gsudo -- powershell -ExecutionPolicy Bypass -File $PSCommandPath"
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
Write-Host "== whisper.cpp (ROCm) install on $env:COMPUTERNAME ==" -ForegroundColor Cyan

$model = Join-Path $Root "models\ggml-large-v3.bin"
if (-not (Test-Path $model)) {
    throw "Model missing at $model. Fetch it (ungated, no token needed):`n" +
          "  curl.exe -L -o `"$model`" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin"
}

$src = Join-Path $Root "whisper.cpp"
$built = Join-Path $src "build-hip\bin\whisper-server.exe"

if (-not $SkipBuild) {
    if (-not (Test-Path "$RocmPath\bin\clang++.exe")) { throw "ROCm HIP SDK not found at $RocmPath" }

    # Ninja ships with VS Build Tools' CMake component. HIP on Windows needs a
    # single-config generator; the VS generator does not drive hipcc correctly.
    $ninja = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio" -Filter "ninja.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $ninja) {
        throw "ninja.exe not found. Install VS Build Tools' C++ workload:`n" +
              "  curl.exe -sL -o `"$env:TEMP\vs_BuildTools.exe`" https://aka.ms/vs/17/release/vs_BuildTools.exe`n" +
              "  & `"$env:TEMP\vs_BuildTools.exe`" --quiet --wait --norestart --force --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended`n" +
              "NOTE: --force matters. Without it the pre-check hits 'machine is busy installing'`n" +
              "and --quiet auto-answers Cancel, which surfaces as a misleading 1618."
    }

    if (-not (Test-Path $src)) { git clone --depth 1 --branch v1.9.2 https://github.com/ggml-org/whisper.cpp $src }

    $env:HIP_PATH = $RocmPath
    $env:PATH = "$RocmPath\bin;C:\Program Files\CMake\bin;" + (Split-Path $ninja.FullName) + ";$env:PATH"
    $env:ROCBLAS_TENSILE_LIBPATH = "$RocmPath\bin\rocblas\library"

    Push-Location $src
    try {
        if (Test-Path "build-hip") { Remove-Item "build-hip" -Recurse -Force }
        cmake -B build-hip -G Ninja `
            -DCMAKE_BUILD_TYPE=Release -DGGML_HIP=ON -DAMDGPU_TARGETS=$GpuTarget `
            -DCMAKE_C_COMPILER="$RocmPath/bin/clang.exe" `
            -DCMAKE_CXX_COMPILER="$RocmPath/bin/clang++.exe" `
            -DWHISPER_BUILD_TESTS=OFF
        if ($LASTEXITCODE -ne 0) { throw "cmake configure failed" }
        cmake --build build-hip -j 8
        if ($LASTEXITCODE -ne 0) { throw "cmake build failed" }
    } finally { Pop-Location }
}

if (-not (Test-Path $built)) { throw "whisper-server.exe not found at $built" }
Write-Host "server binary: $built"

# ------------------------------------------------------------------- firewall
# Private/Domain only - deliberately NOT Public. MB's Ethernet interface is
# classified Public, so the LAN IP stays unreachable and traffic comes over the
# Tailscale interface (Private), which matches Snoop's tailnet-only design.
# PersistentStore because a rule created without it was observed not surviving a reboot.
$ruleName = "Snoop whisper.cpp server ($Port)"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort $Port -Profile Private, Domain -PolicyStore PersistentStore | Out-Null
Write-Host "firewall: inbound TCP $Port (Private/Domain, persistent)"

# -------------------------------------------------------------------- service
$nssm = Find-Nssm
if (Get-Service $ServiceName -ErrorAction SilentlyContinue) {
    & $nssm stop $ServiceName | Out-Null
    Start-Sleep -Seconds 3
} else {
    & $nssm install $ServiceName $built | Out-Null
}
& $nssm set $ServiceName Application $built | Out-Null
# AppDirectory is load-bearing: ggml-base/ggml-cpu/ggml-hip/whisper .dll sit next to
# the exe and resolve relative to it.
& $nssm set $ServiceName AppDirectory (Split-Path $built) | Out-Null
& $nssm set $ServiceName AppParameters "-m `"$model`" --host 0.0.0.0 --port $Port -t 8" | Out-Null
& $nssm set $ServiceName AppEnvironmentExtra `
    "ROCBLAS_TENSILE_LIBPATH=$RocmPath\bin\rocblas\library" `
    "PATH=$RocmPath\bin;$env:SystemRoot\system32;$env:SystemRoot" | Out-Null
& $nssm set $ServiceName DisplayName "Whisper.cpp Server (ROCm/$GpuTarget, Snoop secondary)" | Out-Null
& $nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $nssm set $ServiceName AppStdout "$Root\server.log" | Out-Null
& $nssm set $ServiceName AppStderr "$Root\server.err.log" | Out-Null
& $nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $nssm start $ServiceName | Out-Null

Start-Sleep -Seconds 25
Write-Host ("service $ServiceName -> " + (Get-Service $ServiceName).Status) -ForegroundColor Green

# ---------------------------------------------------------------- verify on GPU
# Exercise it, do not read a status. A Running service and a 200 both stay true when
# the model silently lands on CPU, which is the 2026-05-19 ROCm-migration lesson.
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 25
    Write-Host "local HTTP: $($r.StatusCode)"
} catch { Write-Warning "local HTTP probe failed: $($_.Exception.Message)" }

$log = Get-Content "$Root\server.log", "$Root\server.err.log" -ErrorAction SilentlyContinue
if ($log | Select-String -Pattern "using ROCm0 backend|ROCm devices") {
    Write-Host "GPU CONFIRMED: model is on the ROCm backend" -ForegroundColor Green
} else {
    Write-Warning "Could not confirm the ROCm backend in the logs - it may have fallen back to CPU."
}

Write-Host ""
Write-Host "VERIFY FROM KAYDANSKI, not from here:" -ForegroundColor Cyan
Write-Host "  Invoke-WebRequest http://masterblaster:$Port/ -UseBasicParsing"
Write-Host "If it times out: Tailscale is probably in NoState after a reboot -" -ForegroundColor Yellow
Write-Host "  Start-Process 'C:\Program Files\Tailscale\tailscale-ipn.exe'"
