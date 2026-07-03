@echo off
setlocal enabledelayedexpansion
title CMS Dashboard - First Time Setup

echo ================================================
echo  CMS Grid Resilience Dashboard - Setup
echo ================================================
echo.

cd /d "%~dp0"

REM --- Check Python ---
echo [1/8] Checking Python installation...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.12+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
echo      Python found.

REM --- Create virtual environment ---
echo [2/8] Creating virtual environment...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo      Virtual environment created.
) else (
    echo      Virtual environment already exists.
)

REM --- Install dependencies ---
echo [3/8] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo      Dependencies installed.

REM --- Setup .env file ---
echo [4/8] Configuring API keys...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo.
        echo      Created .env from template.
        echo      Please edit .env and add your API keys:
        echo        - ENW_API_KEY (get from https://electricitynorthwest.opendatasoft.com/)
        echo        - XIAOMI_API_KEY or OPENAI_API_KEY (for AI features)
        echo.
        echo      Press any key to open .env for editing...
        pause >nul
        start notepad .env
        echo      Waiting for you to save .env...
        echo      Press any key when done...
        pause >nul
    ) else (
        echo WARNING: .env.example not found. Creating minimal .env...
        echo ENW_API_KEY=your_api_key_here> .env
        echo XIAOMI_API_KEY=your_api_key_here>> .env
    )
) else (
    echo      .env already exists.
)

REM --- Fetch initial data ---
echo [5/8] Fetching initial outage data...
python data/fetch_outages.py
if !errorlevel! neq 0 (
    echo WARNING: Failed to fetch data. You can retry later.
)

REM --- Train ML model ---
echo [6/8] Training risk prediction model...
if not exist "models\*.pkl" (
    python advanced_charts/risk_model.py
    if !errorlevel! neq 0 (
        echo WARNING: Model training failed. Dashboard will work but risk predictions unavailable.
    )
) else (
    echo      Models already trained.
)

REM --- Build OpenClaw plugin ---
echo [7/8] Building OpenClaw plugin...
if exist "openclaw-plugin\package.json" (
    cd openclaw-plugin
    call npm install >nul 2>&1
    call npm run build >nul 2>&1
    cd ..
    echo      OpenClaw plugin built.
) else (
    echo      OpenClaw plugin not found, skipping.
)

REM --- Configure OpenClaw ---
echo [8/8] Configuring OpenClaw...
call :SetupOpenClaw

REM --- Download nginx ---
echo.
echo Setting up nginx...
if not exist "nginx\nginx.exe" (
    echo      Downloading nginx...
    curl -L -o nginx.zip "https://nginx.org/download/nginx-1.27.4.zip" >nul 2>&1
    if !errorlevel! neq 0 (
        echo WARNING: Failed to download nginx. Dashboard will work without proxy.
    ) else (
        powershell -command "Expand-Archive -Path nginx.zip -DestinationPath nginx-tmp -Force"
        move nginx-tmp\nginx-*\* nginx\ >nul 2>&1
        rmdir /s /q nginx-tmp >nul 2>&1
        del nginx.zip >nul 2>&1
        echo      nginx downloaded.
    )
) else (
    echo      nginx already exists.
)

echo.
echo ================================================
echo  Setup Complete!
echo ================================================
echo.
echo  To start the dashboard, run:
echo    run_dashboard.bat
echo.
echo  OpenClaw WebChat:
echo    http://127.0.0.1:18789/
echo.
echo  See README_OPENCLAW.md for more details.
echo.
pause
exit /b 0

REM =============================================
REM  OpenClaw Configuration Subroutine
REM =============================================
:SetupOpenClaw

REM --- Check if OpenClaw is installed ---
openclaw --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo WARNING: OpenClaw is not installed.
    echo Install it with: npm install -g openclaw@latest
    echo Then run this setup again.
    goto :eof
)

REM --- Get absolute paths ---
set "PROJECT_ROOT=%~dp0"
set "PYTHON_PATH=%PROJECT_ROOT%venv\Scripts\python.exe"
set "TOOLS_DIR=%PROJECT_ROOT%tools"

REM --- Check if OpenClaw config exists ---
set "OPENCLAW_CONFIG=%USERPROFILE%\.openclaw\openclaw.json"
if not exist "%OPENCLAW_CONFIG%" (
    echo.
    echo OpenClaw config not found. Running onboarding...
    openclaw onboard --install-daemon
)

REM --- Read existing config or create new one ---
echo.
echo Configuring OpenClaw plugin...

REM Create a temporary Python script to update config
(
echo import json
echo import os
echo import sys
echo.
echo config_path = os.path.expanduser(r'~\.openclaw\openclaw.json'^)
echo.
echo # Read existing config or create new
echo if os.path.exists(config_path^):
echo     with open(config_path, 'r'^) as f:
echo         config = json.load(f^)
echo else:
echo     config = {}^
echo.
echo # Ensure structure exists
echo if 'gateway' not in config:
echo     config['gateway'] = {
echo         "mode": "local",
echo         "auth": {"mode": "none"},
echo         "port": 18789,
echo         "bind": "loopback",
echo         "controlUi": {
echo             "allowInsecureAuth": True,
echo             "allowedOrigins": ["*"]
echo         }
echo     }^
echo.
echo if 'plugins' not in config:
echo     config['plugins'] = {}^
echo.
echo if 'entries' not in config['plugins']:
echo     config['plugins']['entries'] = {}^
echo.
echo # Update CMS Dashboard plugin
echo config['plugins']['entries']['cms-dashboard'] = {
echo     "enabled": True,
echo     "pythonPath": r'%PYTHON_PATH%',
echo     "toolsDir": r'%TOOLS_DIR%'
echo }^
echo.
echo # Write updated config
echo with open(config_path, 'w'^) as f:
echo     json.dump(config, f, indent=2^)
echo.
echo print(f"Config updated: {config_path}"^)
) > "%TEMP%\update_openclaw_config.py"

python "%TEMP%\update_openclaw_config.py"
if !errorlevel! neq 0 (
    echo ERROR: Failed to update OpenClaw config.
    echo Please manually add this to %OPENCLAW_CONFIG%:
    echo.
    echo   "plugins": {
    echo     "entries": {
    echo       "cms-dashboard": {
    echo         "enabled": true,
    echo         "pythonPath": "%PYTHON_PATH%",
    echo         "toolsDir": "%TOOLS_DIR%"
    echo       }
    echo     }
    echo   }
    echo.
) else (
    echo      OpenClaw plugin configured.
)

del "%TEMP%\update_openclaw_config.py" >nul 2>&1

goto :eof
