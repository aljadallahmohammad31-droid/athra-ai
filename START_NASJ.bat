@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer and add it to PATH.
  pause
  exit /b 1
)

python -m pip show python-docx >nul 2>&1
if errorlevel 1 (
  echo Installing ATHRA dependencies...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

echo Starting ATHRA server...
echo Open http://127.0.0.1:8765
start "" http://127.0.0.1:8765
python app.py
pause
