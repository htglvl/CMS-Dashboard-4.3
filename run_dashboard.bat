@echo off
setlocal enabledelayedexpansion
title CMS Grid Resilience Dashboard

echo ================================================
echo  CMS Grid Resilience Dashboard - Auto Setup
echo ================================================
echo.

cd /d "%~dp0"

REM --- 1. Virtual environment ---
if not exist "venv\Scripts\python.exe" (
    echo [1/7] Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [1/7] Virtual environment already exists.
)

REM --- 2. Dependencies ---
echo [2/7] Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM --- 3. Fetch outage data ---
echo [3/7] Checking for new outage data...
python data/fetch_outages.py

REM --- 4. Fetch flexibility tenders ---
echo [4/7] Checking flexibility tenders...
python data/fetch_flexibility_tenders.py

REM --- 5. Build OpenClaw plugin ---
echo [5/7] Building OpenClaw plugin...
cd openclaw-plugin
call npm install >nul 2>&1
call npm run build >nul 2>&1
cd ..

REM --- 6. Start OpenClaw gateway ---
echo [6/7] Starting OpenClaw gateway...
start "OpenClaw Gateway" cmd /c "call venv\Scripts\activate.bat && openclaw start --plugin openclaw-plugin"
timeout /t 3 /nobreak >nul

REM --- 7. Start Streamlit (internal port 8502) ---
echo [7/7] Starting Streamlit dashboard...
start "Streamlit Dashboard" cmd /c "call venv\Scripts\activate.bat && streamlit run enhanced_app.py --server.port 8502 --server.headless true --server.enableCORS false --server.enableXsrfProtection false"
timeout /t 3 /nobreak >nul

REM --- 8. Start nginx reverse proxy (port 8501) ---
echo [8/8] Starting nginx proxy...
start "Nginx Proxy" cmd /c "cd /d "%~dp0nginx" && nginx.exe"
timeout /t 2 /nobreak >nul

echo.
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo  ================================================
echo.
echo  Press Ctrl+C to stop all services.
echo.

REM Keep running until user presses Ctrl+C
pause >nul

echo.
echo Stopping background services...
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Nginx Proxy*" >nul 2>&1
cd nginx && nginx.exe -s stop 2>nul
echo All services stopped.
pause
