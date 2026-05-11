@echo off
setlocal

set "DASHBOARD_DIR=%~dp0"
set "LOG_DIR=%DASHBOARD_DIR%logs"
set "OUT_LOG=%LOG_DIR%\orthos-readonly-dashboard.out.log"
set "ERR_LOG=%LOG_DIR%\orthos-readonly-dashboard.err.log"

if not defined ORTHOS_BASE_URL set "ORTHOS_BASE_URL=https://chris13600k.tail406192.ts.net/v1"
if not defined LISTEN_HOST set "LISTEN_HOST=127.0.0.1"
if not defined LISTEN_PORT set "LISTEN_PORT=8792"

if not defined ORTHOS_API_TOKEN (
  echo ORTHOS_API_TOKEN is not set.
  echo Set it first, then run this script again.
  echo Example:
  echo   set "ORTHOS_API_TOKEN=your-token-here"
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalAddress %LISTEN_HOST% -LocalPort %LISTEN_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)"') do set "RUN_PID=%%P"
if defined RUN_PID (
  echo Orthos Blackflame dashboard is already running on port %LISTEN_PORT% with PID %RUN_PID%.
  echo URL: http://%LISTEN_HOST%:%LISTEN_PORT%
  exit /b 0
)

cd /d "%DASHBOARD_DIR%"
start "orthos-blackflame-dashboard" /min cmd /c "python orthos-readonly-dashboard.py 1>>"%OUT_LOG%" 2>>"%ERR_LOG%""

timeout /t 2 >nul
for /f "tokens=*" %%P in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalAddress %LISTEN_HOST% -LocalPort %LISTEN_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)"') do set "RUN_PID=%%P"
if defined RUN_PID (
  echo Started Orthos Blackflame dashboard. PID: %RUN_PID%
  echo URL: http://%LISTEN_HOST%:%LISTEN_PORT%
) else (
  echo Failed to start. Check:
  echo   %ERR_LOG%
  exit /b 1
)

endlocal
