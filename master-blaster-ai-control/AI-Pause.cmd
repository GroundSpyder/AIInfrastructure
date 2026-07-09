@echo off
REM AI-Pause.cmd — release Master Blaster's GPU for gaming.
REM Double-click or bind to a hotkey via the desktop shortcut.
title AI Pause - Master Blaster
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Pause.ps1"
timeout /t 3 /nobreak >nul
