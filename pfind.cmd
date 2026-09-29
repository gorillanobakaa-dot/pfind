@echo off
:: pfind launcher for Windows. Put this folder on your PATH, then type:  pfind WHAT [WHERE]
:: Picks a Python that actually starts (the py launcher can point at a Python that is gone),
:: then runs pfind ONCE, so "no matches" (exit 1) never triggers a second run.
setlocal
set "PFIND_PY="
py -3 -c "" >nul 2>&1 && set "PFIND_PY=py -3"
if not defined PFIND_PY python -c "" >nul 2>&1 && set "PFIND_PY=python"
if not defined PFIND_PY (
    echo pfind: no working Python found. Install it from https://www.python.org/downloads/
    echo        or run:  winget install -e --id Python.Python.3.12
    exit /b 9009
)
%PFIND_PY% "%~dp0pfind.py" %*
exit /b %errorlevel%
