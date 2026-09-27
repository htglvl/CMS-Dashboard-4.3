@echo off
setlocal enabledelayedexpansion
title CMS Grid Resilience Dashboard

echo ================================================
echo  CMS Grid Resilience Dashboard
echo ================================================
echo.

cd /d "%~dp0"

REM Retired mode: do not start an unguarded legacy scheduler.
if /I "%~1"=="--prewarm-loop" exit /b 0

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
    echo [1/9] Creating virtual environment...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create venv.
        pause
        exit /b 1
    )
) else (
    echo [1/9] Virtual environment already exists.
)

REM --- 2. Dependencies ---
echo [2/9] Installing dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM --- 3. Fetch outage data ---
REM Deploy before launching services so failures do not leave a partial startup.
echo      Deploying the permanent Cloudflare Worker proxy...
python cloudflare\deploy_worker.py
if errorlevel 1 (
    echo ERROR: Worker deployment failed. Fix the error above and run this script again.
    pause
    exit /b 1
)
set /p CMS_PUBLIC_URL=<worker_url.txt
if not exist "cloudflared.exe" (
    echo      Downloading cloudflared...
    curl --fail -L -o cloudflared.exe.tmp "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if !errorlevel! equ 35 (
        echo      TLS handshake failed; retrying with best-effort revocation checks.
        REM Retains certificate and hostname validation. Only unavailable
        REM revocation-list checks are tolerated by Schannel on this retry.
        curl --ssl-revoke-best-effort --fail -L -o cloudflared.exe.tmp "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    )
    if errorlevel 1 (
        echo ERROR: cloudflared download failed.
        pause
        exit /b 1
    )
    move /y cloudflared.exe.tmp cloudflared.exe >nul
    if errorlevel 1 (
        echo ERROR: Could not save cloudflared.exe. Check folder permissions.
        pause
        exit /b 1
    )
)

echo [3/9] Checking for new outage data...
python data/fetch_outages.py

REM --- 4. Fetch flexibility tenders ---
echo [4/9] Checking flexibility tenders...
python data/fetch_flexibility_tenders.py

REM --- 5. Build OpenClaw plugin ---
echo [5/9] Building OpenClaw plugin...
set CMS_OPENCLAW_ENABLED=0
where openclaw >nul 2>&1
if errorlevel 1 goto :openclaw_unavailable
where npm >nul 2>&1
if errorlevel 1 goto :openclaw_unavailable
cd openclaw-plugin
call npm install
if errorlevel 1 (
    cd ..
    goto :openclaw_unavailable
)
call npm run build
if errorlevel 1 (
    cd ..
    goto :openclaw_unavailable
)
cd ..
set CMS_OPENCLAW_ENABLED=1
goto :openclaw_checked
:openclaw_unavailable
echo      Optional OpenClaw chat unavailable: install OpenClaw and npm, then check the plugin build.
:openclaw_checked

REM --- 6. Download nginx if not present ---
echo [6/9] Checking nginx...
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

REM --- Sync CMS API settings (.env -> ~/.openclaw/openclaw.json) ---
echo      Syncing CMS API settings (baseUrl/key from .env)...
if "%CMS_OPENCLAW_ENABLED%"=="0" goto :openclaw_started
python openclaw-plugin\configure.py
if errorlevel 1 (
    set CMS_OPENCLAW_ENABLED=0
    echo WARNING: OpenClaw configuration failed. Continuing with the dashboard.
    goto :openclaw_started
)

REM --- 7. Start OpenClaw gateway ---
echo [7/9] Starting OpenClaw gateway...
start "OpenClaw Gateway" cmd /c "call venv\Scripts\activate.bat && openclaw start --plugin openclaw-plugin"
timeout /t 3 /nobreak >nul
:openclaw_started

REM --- 8. Start Streamlit (internal port 8502) ---
echo [8/9] Starting Streamlit dashboard...
start "Streamlit Dashboard" cmd /c "call venv\Scripts\activate.bat && streamlit run enhanced_app.py --server.port 8502 --server.headless true --server.enableCORS false --server.enableXsrfProtection false"
timeout /t 3 /nobreak >nul

REM --- Generate nginx config ---
echo      Generating nginx config...
python -c "import json,os;p=os.path.expanduser(r'~\.openclaw\openclaw.json');t=json.load(open(p)).get('gateway',{}).get('auth',{}).get('token','') if os.path.exists(p) else '';c=open(r'nginx\conf\nginx.conf.template').read();open(r'nginx\conf\nginx.conf','w').write(c.replace('__OCLAW_TOKEN__',t))"

REM --- Start OpenClaw Python proxy (port 8503) ---
echo      Starting OpenClaw proxy on port 8503...
start "OpenClaw Proxy" cmd /c "call venv\Scripts\activate.bat && python openclaw_proxy.py"
timeout /t 2 /nobreak >nul

REM --- Kill any old nginx instances and start fresh ---
nginx\nginx.exe -p "%~dp0nginx/" -s quit >nul 2>&1
timeout /t 1 /nobreak >nul
start "Nginx Proxy" cmd /c "cd /d "%~dp0nginx" && nginx.exe"
timeout /t 2 /nobreak >nul

REM --- Pre-warm now and every 24 hours while this server remains running ---
echo      Starting daily dashboard cache pre-warmer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dashboard_prewarm.ps1" -Start

REM --- 9. Start Cloudflare tunnel ---
echo [9/9] Starting Cloudflare tunnel on port 8501...
if not exist "logs" mkdir logs
start "Cloudflare Tunnel" /MIN cmd /c "call venv\Scripts\activate.bat && python -u capture_tunnel_url.py >logs\cloudflare-tunnel.log 2>&1"
python cloudflare\deploy_worker.py --wait
if errorlevel 1 (
    echo WARNING: Public access is not ready. Check logs\cloudflare-tunnel.log.
    echo          Local services remain running for troubleshooting.
)

echo.
echo  ================================================
echo   Dashboard: http://localhost:8501/home
if "%CMS_OPENCLAW_ENABLED%"=="1" echo   OpenClaw:  http://localhost:8501/oclaw
if "%CMS_OPENCLAW_ENABLED%"=="0" echo   OpenClaw:  unavailable - optional dependency not installed or configured
echo   Public:    !CMS_PUBLIC_URL!
echo              Share and bookmark this permanent address.
echo              Address also saved to worker_url.txt
echo  ================================================
echo.
echo  Press any key to stop all services...
echo.

pause >nul

echo.
echo Stopping background services...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dashboard_prewarm.ps1" -Stop
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Cloudflare Tunnel*" /T /F >nul 2>&1
nginx\nginx.exe -p "%~dp0nginx/" -s quit >nul 2>&1
echo All services stopped.
pause
exit /b 0
