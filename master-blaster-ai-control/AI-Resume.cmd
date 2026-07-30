@echo off
REM AI-Resume.cmd - restart Master Blaster's Ollama and warm the default models.
REM Double-click or bind to a hotkey via the desktop shortcut.
REM
REM Needs elevation because AI-Pause now stops the service outright, so resuming
REM has to start it again. Routes through gsudo for the same reason as AI-Pause.
title AI Resume - Master Blaster
where gsudo >nul 2>&1
if %ERRORLEVEL%==0 (
    gsudo powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Resume.ps1"
) else (
    echo [AI-Resume] gsudo not found - retrying unelevated, this will fail if not admin.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Resume.ps1"
)
timeout /t 3 /nobreak >nul
