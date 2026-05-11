@echo off
setlocal

if not defined LISTEN_HOST set "LISTEN_HOST=127.0.0.1"
if not defined LISTEN_PORT set "LISTEN_PORT=8791"

for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalAddress %LISTEN_HOST% -LocalPort %LISTEN_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)"') do set "RUN_PID=%%P"
if not defined RUN_PID (
  echo Orthos read-only dashboard is not running on %LISTEN_HOST%:%LISTEN_PORT%.
  exit /b 0
)

powershell -NoProfile -Command "Stop-Process -Id %RUN_PID% -Force"
echo Stopped Orthos read-only dashboard PID %RUN_PID%.

endlocal
