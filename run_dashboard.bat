@echo off
setlocal enabledelayedexpansion
title CMS Grid Resilience Dashboard

echo ================================================
echo  CMS Grid Resilience Dashboard
echo ================================================
echo.

cd /d "%~dp0"

REM --- Check if setup has been run ---
if not exist ".env" (
    if exist ".env.example" (
        echo ERROR: .env file not found.
        echo Please run setup.bat first, or copy .env.example to .env
        echo and fill in your API keys.
        pause
        exit /b 1
    )
)

REM --- 1. Virtual environment ---
if not exist "venv\Scripts\python.exe" (
    echo [1/10] Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [1/10] Virtual environment already exists.
)

REM --- 2. Dependencies ---
echo [2/10] Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM --- 3. Fetch outage data ---
echo [3/10] Checking for new outage data...
python data/fetch_outages.py

REM --- 4. Fetch flexibility tenders ---
echo [4/10] Checking flexibility tenders...
python data/fetch_flexibility_tenders.py

REM --- 5. Build OpenClaw plugin ---
echo [5/10] Building OpenClaw plugin...
cd openclaw-plugin
call npm install >nul 2>&1
call npm run build >nul 2>&1
cd ..

REM --- 6. Download nginx if not present ---
echo [6/10] Checking nginx...
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

REM --- 7. Download cloudflared if not present ---
echo [7/10] Checking cloudflared...
if not exist "cloudflared.exe" (
    echo      Downloading cloudflared...
    curl -L -o cloudflared.exe "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: Failed to download cloudflared.
        pause
        exit /b 1
    )
    echo      cloudflared downloaded.
) else (
    echo      cloudflared already exists.
)

REM --- 8. Start OpenClaw gateway ---
echo [8/10] Starting OpenClaw gateway...
start "OpenClaw Gateway" cmd /c "call venv\Scripts\activate.bat && openclaw start --plugin openclaw-plugin"
timeout /t 3 /nobreak >nul

REM --- 9. Start Streamlit (internal port 8502) ---
echo [9/10] Starting Streamlit dashboard...
start "Streamlit Dashboard" cmd /c "call venv\Scripts\activate.bat && streamlit run enhanced_app.py --server.port 8502 --server.headless true --server.enableCORS false --server.enableXsrfProtection false"
timeout /t 3 /nobreak >nul

REM --- Generate nginx config ---
echo      Generating nginx config...
python -c "import json,os;p=os.path.expanduser(r'~\.openclaw\openclaw.json');t=json.load(open(p)).get('gateway',{}).get('auth',{}).get('token','');c=open(r'nginx\conf\nginx.conf.template').read();open(r'nginx\conf\nginx.conf','w').write(c.replace('__OCLAW_TOKEN__',t))"

REM --- Start OpenClaw Python proxy (port 8503) ---
echo      Starting OpenClaw proxy on port 8503...
start "OpenClaw Proxy" cmd /c "call venv\Scripts\activate.bat && python openclaw_proxy.py"
timeout /t 2 /nobreak >nul

REM --- Kill any old nginx instances and start fresh ---
wmic process where "name='nginx.exe'" delete >nul 2>&1
timeout /t 1 /nobreak >nul
start "Nginx Proxy" cmd /c "cd /d "%~dp0nginx" && nginx.exe"
timeout /t 2 /nobreak >nul

REM --- 10. Start Cloudflare tunnel ---
echo [10/10] Starting Cloudflare tunnel on port 8501...
start "Cloudflare Tunnel" cmd /c "cloudflared.exe tunnel --url http://localhost:8501"
timeout /t 3 /nobreak >nul

echo.
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo   Tunnel:    Check cloudflared window for the public URL
echo  ================================================
echo.
echo  Press any key to stop all services...
echo.

pause >nul

echo.
echo Stopping background services...
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Cloudflare Tunnel*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
wmic process where "name='cloudflared.exe'" delete >nul 2>&1
echo All services stopped.
pause
