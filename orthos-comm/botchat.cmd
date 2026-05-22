@echo off
REM Wrapper for orthos_comm.py. Add this directory to PATH or copy this .cmd
REM to a directory already on PATH (the wrapper finds the script via its own
REM location).
REM
REM Argument forwarding uses %* (the raw command-line tail). This preserves
REM cmd metacharacters (& | > < ^ etc.) when the *invoking* shell supplied
REM proper quoting -- which is the case for:
REM   - Claude Code slash commands invoked via the Bash tool: `orthos-comm post "$ARGUMENTS"`
REM   - PowerShell with quoted args: `orthos-comm post "hello & world"`
REM   - cmd with quoted args:        `orthos-comm post "hello & world"`
REM
REM It does NOT magically fix bare-cmd usage that omits quotes:
REM   `orthos-comm post hello & world`  -- cmd splits on the `&` before this
REM script ever sees it. That's standard cmd behavior; quote your messages.
setlocal
set "SCRIPT_DIR=%~dp0"
set "ORTHOS_COMM_PY=%SCRIPT_DIR%orthos_comm.py"
if not exist "%ORTHOS_COMM_PY%" (
    echo orthos-comm: cannot find orthos_comm.py next to this wrapper at "%ORTHOS_COMM_PY%" 1>&2
    exit /b 2
)
REM Prefer the Windows py launcher (which honors shebangs / version pins);
REM fall back to `python` on PATH. Note: we deliberately do not nest the call
REM inside an `if (...)` block -- %ERRORLEVEL% inside one expands at parse time,
REM which would mask the actual Python exit code.
where py >nul 2>nul && goto use_py
python "%ORTHOS_COMM_PY%" %*
exit /b %ERRORLEVEL%

:use_py
py -3 "%ORTHOS_COMM_PY%" %*
exit /b %ERRORLEVEL%
