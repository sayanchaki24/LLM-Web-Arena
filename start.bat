@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo   Starting BestResponse Multi-LLM Web Aggregator
echo ========================================================

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Setting up .venv...
    python -m venv .venv
    echo Installing dependencies...
    .venv\Scripts\pip.exe install -r requirements.txt
    .venv\Scripts\playwright.exe install chromium
)

echo Launching BestResponse Dashboard...
.venv\Scripts\python.exe run.py

pause
