@echo off
REM AI-Resume.cmd — warm Master Blaster's default Ollama models back into VRAM.
REM Double-click or bind to a hotkey via the desktop shortcut.
title AI Resume - Master Blaster
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AI-Resume.ps1"
timeout /t 3 /nobreak >nul
