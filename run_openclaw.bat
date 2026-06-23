@echo off
REM ── CMS Dashboard — OpenClaw Gateway Launcher ───────────────────────
REM
REM  Prerequisites:
REM    1. Node.js 22+ installed
REM    2. OpenClaw installed globally:  npm install -g openclaw@latest
REM    3. XIAOMI_API_KEY set in .env (or OPENAI_API_KEY / ANTHROPIC_API_KEY)
REM
REM  First-time setup:
REM    openclaw onboard --install-daemon
REM
REM  Then run this script to start the gateway with the CMS plugin.
REM ─────────────────────────────────────────────────────────────────────

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║  CMS Dashboard — OpenClaw Gateway                       ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Navigate to project root
cd /d "%~dp0"

REM Check Node.js is available
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js not found. Please install Node.js 22+.
    pause
    exit /b 1
)

REM Check OpenClaw is installed
where openclaw >nul 2>&1
if errorlevel 1 (
    echo ERROR: OpenClaw not found. Install with: npm install -g openclaw@latest
    pause
    exit /b 1
)

REM Set plugin path
set PLUGIN_DIR=%~dp0openclaw-plugin

echo Starting OpenClaw gateway with CMS Dashboard plugin...
echo Plugin directory: %PLUGIN_DIR%
echo.
echo WebChat UI will be available at: http://127.0.0.1:18789/
echo.

REM Start OpenClaw with the plugin
openclaw start --plugin "%PLUGIN_DIR%"

pause
