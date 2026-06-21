@echo off
setlocal
title CMS Grid Resilience Dashboard

echo ================================================
echo  CMS Grid Resilience Dashboard - Auto Setup
echo ================================================
echo.

REM --- Navigate to script directory ---
cd /d "%~dp0"

REM -------------------------------------------------------
REM  1. Create virtual environment if it doesn't exist
REM -------------------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create venv. Is Python installed and in PATH?
        pause
        exit /b 1
    )
    echo      Done.
) else (
    echo [1/4] Virtual environment already exists.
)

REM -------------------------------------------------------
REM  2. Activate venv and install/update dependencies
REM -------------------------------------------------------
echo [2/4] Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo      Done.

REM -------------------------------------------------------
REM  3. Run daily outage fetch (incremental, skips if recent)
REM -------------------------------------------------------
echo [3/4] Checking for new outage data...
python fetch_outages.py
echo      Done.

REM -------------------------------------------------------
REM  4. Launch the Streamlit dashboard
REM -------------------------------------------------------
echo [4/4] Launching dashboard...
echo.
echo  Dashboard will open in your browser.
echo  Press Ctrl+C here to stop it.
echo.
streamlit run enhanced_app.py

echo.
echo Dashboard stopped.
pause
