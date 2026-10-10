@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto launch
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install .
if errorlevel 1 goto error
:launch
".venv\Scripts\python.exe" -c "import scipy, CoolProp" >nul 2>nul
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install .
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import urllib.request,webbrowser; r=urllib.request.urlopen('http://127.0.0.1:8765/api/cases',timeout=1); assert r.headers.get('Server','').startswith('FrostLens/'); webbrowser.open('http://127.0.0.1:8765')" >nul 2>nul
if not errorlevel 1 exit /b 0
".venv\Scripts\python.exe" -m frostlens serve --open
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo FrostLens could not start. Install Python 3.11+ and check the message above.
echo For manual setup, see README.md.
pause
exit /b 1
