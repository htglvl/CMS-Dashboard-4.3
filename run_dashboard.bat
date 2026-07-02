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
    echo [1/8] Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [1/8] Virtual environment already exists.
)

REM --- 2. Dependencies ---
echo [2/8] Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM --- 3. Fetch outage data ---
echo [3/8] Checking for new outage data...
python data/fetch_outages.py

REM --- 4. Fetch flexibility tenders ---
echo [4/8] Checking flexibility tenders...
python data/fetch_flexibility_tenders.py

REM --- 5. Build OpenClaw plugin ---
echo [5/8] Building OpenClaw plugin...
cd openclaw-plugin
call npm install >nul 2>&1
call npm run build >nul 2>&1
cd ..

REM --- 6. Download nginx if not present ---
echo [6/8] Checking nginx...
if not exist "nginx\nginx.exe" (
    echo      Downloading nginx...
    curl -L -o nginx.zip "https://nginx.org/download/nginx-1.27.4.zip" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: Failed to download nginx.
        pause
        exit /b 1
    )
    powershell -command "Expand-Archive -Path nginx.zip -DestinationPath nginx-tmp -Force"
    move nginx-tmp\nginx-*\* nginx\ >nul 2>&1
    rmdir /s /q nginx-tmp >nul 2>&1
    del nginx.zip >nul 2>&1
    echo      nginx downloaded.
) else (
    echo      nginx already exists.
)

REM --- 7. Start OpenClaw gateway ---
echo [7/8] Starting OpenClaw gateway...
start "OpenClaw Gateway" cmd /c "call venv\Scripts\activate.bat && openclaw start --plugin openclaw-plugin"
timeout /t 3 /nobreak >nul

REM --- 8. Start Streamlit (internal port 8502) ---
echo [8/8] Starting Streamlit dashboard...
start "Streamlit Dashboard" cmd /c "call venv\Scripts\activate.bat && streamlit run enhanced_app.py --server.port 8502 --server.headless true --server.enableCORS false --server.enableXsrfProtection false"
timeout /t 3 /nobreak >nul

REM --- Generate nginx config with OpenClaw token ---
echo      Generating nginx config...
python -c "import json,os;p=os.path.expanduser(r'~\.openclaw\openclaw.json');t=json.load(open(p)).get('gateway',{}).get('auth',{}).get('token','');c=open(r'nginx\conf\nginx.conf.template').read();open(r'nginx\conf\nginx.conf','w').write(c.replace('__OCLAW_TOKEN__',t))"

REM --- Kill any old nginx instances and start fresh ---
wmic process where "name='nginx.exe'" delete >nul 2>&1
timeout /t 1 /nobreak >nul
start "Nginx Proxy" cmd /c "cd /d "%~dp0nginx" && nginx.exe"
timeout /t 2 /nobreak >nul

echo.
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo  ================================================
echo.
echo  Press any key to stop all services...
echo.

pause >nul

echo.
echo Stopping background services...
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
echo All services stopped.
pause
