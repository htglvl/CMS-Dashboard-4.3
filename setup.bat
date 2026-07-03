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
if exist ".env" goto :env_exists
if exist ".env.example" goto :env_from_template
goto :env_create_minimal

:env_exists
echo      .env already exists, skipping.
goto :env_done

:env_from_template
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
goto :env_done

:env_create_minimal
echo WARNING: .env.example not found. Creating minimal .env...
echo ENW_API_KEY=your_api_key_here> .env
echo XIAOMI_API_KEY=your_api_key_here>> .env
echo      Please edit .env with your API keys later.

:env_done

REM --- Download nginx (do this early, before data fetch) ---
echo.
echo [5/8] Setting up nginx...
if exist "nginx\nginx.exe" (
    echo      nginx already exists.
    goto :nginx_done
)

echo      Downloading nginx...
curl -L -o nginx.zip "https://nginx.org/download/nginx-1.27.4.zip"
if !errorlevel! neq 0 (
    echo WARNING: Failed to download nginx. Dashboard will work without proxy.
    goto :nginx_done
)

echo      Extracting nginx...
powershell -command "Expand-Archive -Path nginx.zip -DestinationPath nginx-tmp -Force"

REM Copy nginx files into nginx folder
xcopy "nginx-tmp\nginx-1.27.4\*" "nginx\" /E /I /Y >nul 2>&1

REM Replace default nginx.conf with our template
copy "nginx\conf\nginx.conf.template" "nginx\conf\nginx.conf" >nul 2>&1

rmdir /s /q nginx-tmp >nul 2>&1
del nginx.zip >nul 2>&1
echo      nginx downloaded.

:nginx_done

REM --- Fetch initial data ---
echo.
echo [6/8] Fetching initial outage data...
findstr /C:"your_api_key_here" .env >nul 2>&1
if !errorlevel! equ 0 (
    echo WARNING: API key not configured in .env
    echo      Please edit .env and set ENW_API_KEY before fetching data.
    echo      Skipping data fetch...
) else (
    python data/fetch_outages.py
    if !errorlevel! neq 0 (
        echo WARNING: Failed to fetch data. You can retry later.
    )
)

REM --- Train ML model (only if data exists) ---
echo.
echo [7/8] Training risk prediction model...
if exist "data\df_cleaned.csv" (
    if not exist "models\*.pkl" (
        python advanced_charts/risk_model.py
        if !errorlevel! neq 0 (
            echo WARNING: Model training failed. Dashboard will work but risk predictions unavailable.
        )
    ) else (
        echo      Models already trained.
    )
) else (
    echo WARNING: No data file found. Skipping model training.
    echo      Run setup.bat again after configuring API key and fetching data.
)

REM --- Build and configure OpenClaw plugin ---
echo.
echo [8/8] Configuring OpenClaw...
if exist "openclaw-plugin\package.json" (
    cd openclaw-plugin
    call npm install >nul 2>&1
    call npm run build >nul 2>&1
    cd ..
    echo      OpenClaw plugin built.
    
    REM Configure OpenClaw
    openclaw --version >nul 2>&1
    if !errorlevel! equ 0 (
        python openclaw-plugin\configure.py
        if !errorlevel! equ 0 (
            echo      OpenClaw configured.
        ) else (
            echo WARNING: Failed to configure OpenClaw. See README_OPENCLAW.md
        )
    ) else (
        echo WARNING: OpenClaw not installed. Install with: npm install -g openclaw@latest
    )
) else (
    echo      OpenClaw plugin not found, skipping.
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
