@echo off
REM AI-Pause.cmd - release Master Blaster's GPU for gaming.
REM Double-click or bind to a hotkey via the desktop shortcut.
REM
REM Stopping a Windows service needs elevation, so this routes through gsudo
REM (CacheMode auto, installed 2026-05-19) to avoid a UAC click every time.
REM Falls back to a plain call if gsudo is missing, which will fail loudly
REM rather than silently leaving the GPU held.
title AI Pause - Master Blaster
where gsudo >nul 2>&1
if %ERRORLEVEL%==0 (
    gsudo powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Pause.ps1"
) else (
    echo [AI-Pause] gsudo not found - retrying unelevated, this will fail if not admin.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Pause.ps1"
)
timeout /t 3 /nobreak >nul
