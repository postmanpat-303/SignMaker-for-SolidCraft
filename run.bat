@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw "%~dp0SignMaker.pyw"
  exit /b 0
)

where py >nul 2>&1
if %errorlevel%==0 (
  start "" py -3w "%~dp0SignMaker.pyw"
  exit /b 0
)

echo Python was not found.
echo Install Python 3.10 or newer from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then run:
echo     py -3 -m pip install -r requirements.txt
pause
exit /b 1
