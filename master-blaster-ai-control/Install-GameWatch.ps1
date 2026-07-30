# Install-GameWatch.ps1 - register Game-Watch.ps1 as an always-on scheduled task.
#
# Runs as SYSTEM at boot so it can Stop-Service/Start-Service without a UAC
# prompt and without depending on Kyle being logged in. Restarts itself if the
# process dies, because a dead watcher means an ungated GPU.
#
# Usage (elevated, or via gsudo):
#   .\Install-GameWatch.ps1              install or update the task
#   .\Install-GameWatch.ps1 -Uninstall   remove the task
#   .\Install-GameWatch.ps1 -Status      show task state and recent gate log

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Status,
    [int]$IntervalSeconds    = 10,
    [int]$ResumeGraceSeconds = 60
)

$ErrorActionPreference = 'Stop'

$TaskName   = 'Falkensteink-GameWatch'
$WatchPath  = Join-Path $PSScriptRoot 'Game-Watch.ps1'
$GateLog    = Join-Path $env:ProgramData 'falkensteink\gpu-gate.log'

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-OrphanWatchers {
    <#
      Kill any Game-Watch processes still running outside the scheduled task.

      Unregister-ScheduledTask does NOT terminate the process the task started,
      so every reinstall used to leave the previous watcher running forever. It
      is then invisible to the task scheduler: it will not be restarted, will
      not be stopped, and just quietly multiplies the poll and heartbeat rate.
      Observed 2026-07-30: three concurrent watchers after three reinstalls.

      The cross-process mutex kept the gate state correct throughout, but
      orphans are still wrong - they are unmanaged, and a stale one running old
      code after an upgrade would be genuinely dangerous.
    #>
    $mine = $PID
    $orphans = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*Game-Watch.ps1*' -and $_.ProcessId -ne $mine })
    if ($orphans.Count -eq 0) { return }
    Write-Host "Found $($orphans.Count) running watcher process(es), stopping them ..." -ForegroundColor DarkGray
    foreach ($o in $orphans) {
        try {
            Stop-Process -Id $o.ProcessId -Force -ErrorAction Stop
            Write-Host "  stopped pid $($o.ProcessId)" -ForegroundColor DarkGray
        } catch {
            Write-Host "  WARNING could not stop pid $($o.ProcessId): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    Start-Sleep -Seconds 1
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "Task '$TaskName' is NOT installed." -ForegroundColor Yellow
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "Task     : $TaskName"                  -ForegroundColor Cyan
        Write-Host "State    : $($task.State)"
        Write-Host "Last run : $($info.LastRunTime)"
        Write-Host "Last rc  : $($info.LastTaskResult)"
    }
    Write-Host ''
    if (Test-Path -LiteralPath $GateLog) {
        Write-Host "--- last 20 gate log lines ---" -ForegroundColor DarkGray
        Get-Content -LiteralPath $GateLog -Tail 20
    } else {
        Write-Host "No gate log yet at $GateLog" -ForegroundColor DarkGray
    }
    exit 0
}

if (-not (Test-Elevated)) {
    Write-Host 'This script must run elevated. Re-run via: gsudo powershell -File Install-GameWatch.ps1' -ForegroundColor Red
    exit 1
}

if ($Uninstall) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Host "Task '$TaskName' was not installed. Nothing to do." -ForegroundColor Yellow
        exit 0
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Stop-OrphanWatchers
    Write-Host "Removed task '$TaskName'." -ForegroundColor Green
    Write-Host 'NOTE: the GPU gate is no longer automatic. Ollama can now load models during games.' -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path -LiteralPath $WatchPath)) {
    Write-Host "Cannot find Game-Watch.ps1 at $WatchPath" -ForegroundColor Red
    exit 1
}

$argLine = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -IntervalSeconds {1} -ResumeGraceSeconds {2}' -f `
    $WatchPath, $IntervalSeconds, $ResumeGraceSeconds

$action    = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

# ExecutionTimeLimit 0 = never kill it, this is a long-running loop.
# RestartCount/Interval bring it back if the process dies, since a dead watcher
# silently un-gates the GPU.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Write-Host "Task exists, replacing ..." -ForegroundColor DarkGray
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
# Must come AFTER unregister so the task cannot restart what we are killing.
Stop-OrphanWatchers

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Stops Ollama while a game is running so it cannot take the GPU mid-session, then restarts and re-warms it afterwards.' | Out-Null

# The gate only works if gate-aware code is the ONLY thing that starts Ollama.
# NSSM installs services as Automatic by default, which means every reboot
# starts Ollama before (or regardless of) the watcher's opinion. Hand start
# control to the gate.
$svc = Get-Service -Name 'OllamaService' -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    Write-Host "WARNING: OllamaService not found - the gate has nothing to control." -ForegroundColor Yellow
} else {
    $startType = (Get-CimInstance -ClassName Win32_Service -Filter "Name='OllamaService'").StartMode
    if ($startType -ne 'Manual') {
        Set-Service -Name 'OllamaService' -StartupType Manual
        Write-Host "Set OllamaService startup type to Manual (was $startType)." -ForegroundColor Green
        Write-Host "  The watcher now owns starting it, so a reboot mid-game cannot un-gate the GPU." -ForegroundColor DarkGray
    }
}

Start-ScheduledTask -TaskName $TaskName

# Verify it actually came up rather than trusting Register/Start to have worked.
# A task that silently fails to launch leaves the GPU ungated with no signal.
$running = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 1
    if ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Running') { $running = $true; break }
}
if (-not $running) {
    Write-Host "ERROR: task registered but is not in the Running state." -ForegroundColor Red
    Write-Host "The GPU is NOT gated. Check Task Scheduler history for $TaskName." -ForegroundColor Red
    exit 1
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Installed and started '$TaskName'." -ForegroundColor Green
Write-Host "  interval     : ${IntervalSeconds}s"
Write-Host "  resume grace : ${ResumeGraceSeconds}s"
Write-Host "  watchlist    : $(Join-Path $PSScriptRoot 'games.json')"
Write-Host "  gate log     : $GateLog"
Write-Host "  last result  : $($info.LastTaskResult)"
Write-Host ''
Write-Host 'Check state any time with: .\Game-Watch.ps1 -Status' -ForegroundColor DarkGray
exit 0
