@echo off
setlocal
cd /d "%~dp0"
python -m pip show python-docx >nul 2>&1
if errorlevel 1 (
  echo Installing project dependencies...
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
echo Starting NASJ Impact Analyzer locally...
echo Open http://127.0.0.1:8765 in your browser.
python app.py
pause
