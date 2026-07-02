@echo off
setlocal enabledelayedexpansion
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
    echo [1/6] Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv. Is Python installed and in PATH?
        pause
        exit /b 1
    )
    echo      Done.
) else (
    echo [1/6] Virtual environment already exists.
)

REM -------------------------------------------------------
REM  2. Activate venv and install/update dependencies
REM -------------------------------------------------------
echo [2/6] Installing dependencies...
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
echo [3/6] Checking for new outage data...
python fetch_outages.py
echo      Done.

REM -------------------------------------------------------
REM  4. Start OpenClaw gateway (background)
REM -------------------------------------------------------
echo [4/6] Starting OpenClaw gateway...
start "OpenClaw Gateway" cmd /c "call venv\Scripts\activate.bat && openclaw start --plugin openclaw-plugin"
echo      OpenClaw starting on port 18789...

REM Give OpenClaw a moment to start
timeout /t 3 /nobreak >nul

REM -------------------------------------------------------
REM  5. Start Streamlit on internal port 8502 (background)
REM -------------------------------------------------------
echo [5/6] Starting Streamlit dashboard...
start "Streamlit Dashboard" cmd /c "call venv\Scripts\activate.bat && streamlit run enhanced_app.py --server.port 8502 --server.headless true"
echo      Streamlit starting on port 8502...

REM Give Streamlit a moment to start
timeout /t 3 /nobreak >nul

REM -------------------------------------------------------
REM  6. Start reverse proxy on port 8501 (foreground)
REM -------------------------------------------------------
echo [6/6] Starting reverse proxy...
echo.
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo  ================================================
echo.
echo  Press Ctrl+C to stop all services.
echo.

python proxy_server.py

echo.
echo Stopping background services...
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
echo All services stopped.
pause
