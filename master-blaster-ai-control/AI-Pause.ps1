# AI-Pause.ps1 - release Master Blaster's GPU for gaming, and make it STICK.
#
# 2026-07-30 rewrite. The previous version unloaded models via keep_alive=0 and
# left the service running, with a header comment conceding "first request after
# pause will reload". That was the bug: the fleet gateway load-balances
# fleet/embed onto this box and routes all of fleet/chat-quality here, so an
# ordinary background embed job dragged ~9-11 GB back into VRAM within minutes,
# mid-game. Unloading is not a gate.
#
# This version stops OllamaService and records a manual pause in the shared gate
# state. A stopped service refuses connections, which additionally lets the
# LiteLLM gateway cooldown this backend cleanly instead of hammering a half-alive
# node (that failure mode produced 2,710 identical Bug Fairy reports).
#
# A manual pause outranks the automatic game watcher: Game-Watch.ps1 will not
# auto-resume a pause it did not create. Release it with AI-Resume.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'GpuGate.ps1')

function Write-Status($msg, $color = 'Cyan') {
    Write-Host "[AI-Pause] $msg" -ForegroundColor $color
}

if (-not (Enter-GateLock)) {
    Write-Status 'Could not take the gate lock (another gate operation is in progress).' 'Red'
    Write-Status 'Wait a few seconds and press Ctrl+Alt+P again.' 'Yellow'
    exit 1
}

try {

$svc = Get-OllamaService
if ($null -eq $svc) {
    Write-Status 'OllamaService not found on this machine.' 'Red'
    Write-GateLog 'manual pause requested but OllamaService is not installed' 'ERROR'
    exit 1
}

Write-Status 'Stopping OllamaService to release the GPU ...'

# Stop-OllamaHard verifies the port is closed, so a $true here means the GPU is
# genuinely free, not merely that the service reported Stopped.
if (-not (Stop-OllamaHard)) {
    Write-Status 'FAILED to release the GPU. Ollama may still be holding VRAM.' 'Red'
    Write-Status 'Try running this as administrator, or check OllamaService.' 'Yellow'
    # Do NOT record a pause we did not achieve. Claiming 'paused' here would tell
    # the watcher the job is done and stop it from retrying.
    Write-GateLog 'manual pause FAILED - GPU not released' 'ERROR'
    Publish-GateState -State 'available' -Owner $script:OWNER_MANUAL `
        -Reason 'manual pause failed, GPU still held' `
        -Alert 'AI-Pause could not stop OllamaService. The GPU is still held.' | Out-Null
    exit 1
}

Set-GateState -State 'paused' -Owner $script:OWNER_MANUAL -Reason 'manual pause (hotkey)' | Out-Null
Publish-GateState -State 'paused' -Owner $script:OWNER_MANUAL -Reason 'manual pause (hotkey)' | Out-Null
Write-GateLog 'manual pause applied'

Write-Status 'GPU released for gaming. Pause will HOLD until you run AI-Resume.' 'Green'
exit 0

} finally {
    Exit-GateLock
}
