# Cloudflare Tunnel Design

**Date:** 2026-07-11
**Branch:** `cloudflare-migrate`
**Status:** Draft

## Problem

The CMS Dashboard uses `ngrok.exe` to expose the local nginx server (port 8501) to the internet. This has several issues:

- **Random URL on every restart** — no config file, so the public URL changes each time
- **31 MB binary committed to git** — bloats the repository
- **Session time limits** — free tier cuts off after ~2 hours
- **No persistent tunnel** — URL is lost when ngrok restarts

## Solution

Replace ngrok with Cloudflare Tunnel (`cloudflared`) as a drop-in replacement. Use a **named tunnel** for a stable `*.cfargotunnel.com` subdomain that persists across restarts.

## Architecture

```
Before:
User → ngrok (random URL) → nginx (8501) → Streamlit (8502)
                                           → OpenClaw proxy (8503)

After:
User → Cloudflare Tunnel (stable URL) → nginx (8501) → Streamlit (8502)
                                                      → OpenClaw proxy (8503)
```

No changes to nginx, Streamlit, or OpenClaw proxy. Only the tunnel layer changes.

## Changes

### 1. `run_dashboard.bat` — Add cloudflared download step

Insert a new step (similar to nginx download logic) that checks for `cloudflared.exe` and downloads it if missing:

```bat
REM --- Download cloudflared if not present ---
echo [X/10] Checking cloudflared...
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
```

### 2. `run_dashboard.bat` — Replace ngrok step with cloudflared

**Before (lines 106-109):**
```bat
REM --- 9. Start ngrok tunnel ---
echo [9/9] Starting ngrok tunnel on port 8501...
start "Ngrok Tunnel" cmd /c "cd /d "%~dp0" && ngrok.exe http 8501"
timeout /t 3 /nobreak >nul
```

**After:**
```bat
REM --- 10. Start Cloudflare tunnel ---
echo [10/10] Starting Cloudflare tunnel on port 8501...
start "Cloudflare Tunnel" cmd /c "cloudflared.exe tunnel run cms-dashboard"
timeout /t 3 /nobreak >nul
```

### 3. `run_dashboard.bat` — Update status output

**Before (lines 112-116):**
```bat
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo   Ngrok:     Check http://127.0.0.1:4040 for the public URL
echo  ================================================
```

**After:**
```bat
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo   Tunnel:    https://<assigned-subdomain>.cfargotunnel.com
echo  ================================================
```

### 4. `run_dashboard.bat` — Update shutdown section

**Before (lines 125-131):**
```bat
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Ngrok Tunnel*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
wmic process where "name='ngrok.exe'" delete >nul 2>&1
```

**After:**
```bat
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Cloudflare Tunnel*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
wmic process where "name='cloudflared.exe'" delete >nul 2>&1
```

### 5. `run_dashboard.bat` — Update step counter

Renumber all steps from `[X/9]` to `[X/10]` to account for the new cloudflared download step.

### 6. `.gitignore` — Add cloudflared

```gitignore
# cloudflared (downloaded at runtime)
cloudflared.exe
```

### 7. Remove `ngrok.exe` from git tracking

```bash
git rm --cached ngrok.exe
```

This removes the 31 MB binary from the repository while keeping it on disk (if still needed for other projects).

## First-Time Setup

These steps are manual and only need to be done once per machine. Document in `README.md`:

```bash
# 1. Authenticate with Cloudflare (opens browser)
cloudflared.exe tunnel login

# 2. Create the named tunnel (outputs a tunnel UUID and assigns a *.cfargotunnel.com subdomain)
cloudflared.exe tunnel create cms-dashboard

# 3. Route DNS — use the subdomain Cloudflare assigned in step 2
cloudflared.exe tunnel route dns cms-dashboard <assigned-subdomain>.cfargotunnel.com
```

After this, the tunnel config is stored in `%USERPROFILE%\.cloudflared\config.yml` and `run_dashboard.bat` will connect automatically.

> **Note:** The `*.cfargotunnel.com` subdomain is auto-assigned by Cloudflare in step 2. You cannot choose it. Check the output of `tunnel create` for the assigned URL.

## What Stays the Same

- nginx config and routing (port 8501)
- Streamlit on port 8502
- OpenClaw proxy on port 8503
- All other startup steps in `run_dashboard.bat`
- `setup.bat` (no changes needed)

## Benefits

| | ngrok free | Cloudflare Tunnel free |
|---|---|---|
| Session limit | ~2 hours | None |
| Stable URL | ❌ | ✅ |
| Bandwidth | Limited | Unlimited |
| Binary size | 31 MB (committed) | ~35 MB (gitignored) |
| Config | None | Named tunnel, persistent |

## Risks

- **Cloudflare account required** — user confirmed they have one
- **First-time setup is manual** — `cloudflared tunnel login` opens a browser, can't be automated in a .bat script
- **Named tunnel must exist** — `run_dashboard.bat` will fail if the tunnel hasn't been created yet (error message will be clear)
