# Cloudflare Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ngrok with Cloudflare Tunnel in `run_dashboard.bat` for a stable public URL.

**Architecture:** Drop-in replacement — swap the tunnel layer only. nginx, Streamlit, and OpenClaw proxy remain unchanged. `cloudflared.exe` is downloaded at runtime (like nginx) and runs a named tunnel.

**Tech Stack:** Windows batch scripts, cloudflared (Cloudflare Tunnel client)

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `run_dashboard.bat` | Modify | Replace ngrok with cloudflared, renumber steps, update shutdown |
| `.gitignore` | Modify | Add `cloudflared.exe` |
| `ngrok.exe` | Remove from git | `git rm --cached` the 31 MB binary |

---

### Task 1: Update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add cloudflared.exe to .gitignore**

Open `.gitignore` and add after the nginx section (around line 84):

```gitignore
# cloudflared (downloaded at runtime)
cloudflared.exe
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add cloudflared.exe to .gitignore"
```

---

### Task 2: Remove ngrok.exe from git tracking

**Files:**
- Remove from tracking: `ngrok.exe`

- [ ] **Step 1: Remove ngrok.exe from git index**

```bash
git rm --cached ngrok.exe
```

This removes the file from git tracking but keeps it on disk.

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove ngrok.exe from git tracking"
```

---

### Task 3: Update `run_dashboard.bat` — Renumber steps

**Files:**
- Modify: `run_dashboard.bat`

The current script has 9 steps. Adding a cloudflared download step makes it 10. Renumber all existing step labels.

- [ ] **Step 1: Change step counter in venv check (line 25)**

Change:
```bat
echo [1/9] Creating virtual environment...
```
To:
```bat
echo [1/10] Creating virtual environment...
```

- [ ] **Step 2: Change step counter in venv exists (line 33)**

Change:
```bat
echo [1/9] Virtual environment already exists.
```
To:
```bat
echo [1/10] Virtual environment already exists.
```

- [ ] **Step 3: Change step counter in dependencies (line 37)**

Change:
```bat
echo [2/9] Installing dependencies...
```
To:
```bat
echo [2/10] Installing dependencies...
```

- [ ] **Step 4: Change step counter in fetch outages (line 48)**

Change:
```bat
echo [3/9] Checking for new outage data...
```
To:
```bat
echo [3/10] Checking for new outage data...
```

- [ ] **Step 5: Change step counter in fetch tenders (line 52)**

Change:
```bat
echo [4/9] Checking flexibility tenders...
```
To:
```bat
echo [4/10] Checking flexibility tenders...
```

- [ ] **Step 6: Change step counter in OpenClaw plugin (line 56)**

Change:
```bat
echo [5/9] Building OpenClaw plugin...
```
To:
```bat
echo [5/10] Building OpenClaw plugin...
```

- [ ] **Step 7: Change step counter in nginx check (line 63)**

Change:
```bat
echo [6/9] Checking nginx...
```
To:
```bat
echo [6/10] Checking nginx...
```

- [ ] **Step 8: Change step counter in OpenClaw gateway (line 82)**

Change:
```bat
echo [7/9] Starting OpenClaw gateway...
```
To:
```bat
echo [7/10] Starting OpenClaw gateway...
```

- [ ] **Step 9: Change step counter in Streamlit (line 87)**

Change:
```bat
echo [8/9] Starting Streamlit dashboard...
```
To:
```bat
echo [8/10] Starting Streamlit dashboard...
```

---

### Task 4: Add cloudflared download step to `run_dashboard.bat`

**Files:**
- Modify: `run_dashboard.bat`

Insert a new step after the nginx download block (after line 79) and before the OpenClaw gateway step (line 81).

- [ ] **Step 1: Insert cloudflared download block**

After line 79 (`echo      nginx already exists.` and closing paren), insert:

```bat

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
```

- [ ] **Step 2: Renumber remaining steps**

After inserting the new step, renumber the subsequent steps:
- Old `[7/10]` (OpenClaw gateway) → `[8/10]`
- Old `[8/10]` (Streamlit) → `[9/10]`
- New ngrok replacement step → `[10/10]`

---

### Task 5: Replace ngrok step with cloudflared in `run_dashboard.bat`

**Files:**
- Modify: `run_dashboard.bat` (lines 106-109)

- [ ] **Step 1: Replace ngrok launch with cloudflared**

Change:
```bat
REM --- 9. Start ngrok tunnel ---
echo [9/9] Starting ngrok tunnel on port 8501...
start "Ngrok Tunnel" cmd /c "cd /d "%~dp0" && ngrok.exe http 8501"
timeout /t 3 /nobreak >nul
```

To:
```bat
REM --- 10. Start Cloudflare tunnel ---
echo [10/10] Starting Cloudflare tunnel on port 8501...
start "Cloudflare Tunnel" cmd /c "cloudflared.exe tunnel run cms-dashboard"
timeout /t 3 /nobreak >nul
```

- [ ] **Step 2: Commit**

```bash
git add run_dashboard.bat
git commit -m "feat: replace ngrok with cloudflared tunnel"
```

---

### Task 6: Update status output in `run_dashboard.bat`

**Files:**
- Modify: `run_dashboard.bat` (lines 112-116)

- [ ] **Step 1: Replace ngrok URL reference**

Change:
```bat
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo   Ngrok:     Check http://127.0.0.1:4040 for the public URL
echo  ================================================
```

To:
```bat
echo  ================================================
echo   Dashboard: http://localhost:8501/home
echo   OpenClaw:  http://localhost:8501/oclaw
echo   Tunnel:    https://cms-dashboard.cfargotunnel.com
echo  ================================================
```

> **Note:** The actual subdomain is assigned by Cloudflare during first-time setup. The user should replace this with their assigned subdomain after running `cloudflared tunnel create cms-dashboard`.

- [ ] **Step 2: Commit**

```bash
git add run_dashboard.bat
git commit -m "fix: update status output for cloudflare tunnel"
```

---

### Task 7: Update shutdown section in `run_dashboard.bat`

**Files:**
- Modify: `run_dashboard.bat` (lines 125-131)

- [ ] **Step 1: Replace ngrok shutdown with cloudflared**

Change:
```bat
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Ngrok Tunnel*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
wmic process where "name='ngrok.exe'" delete >nul 2>&1
```

To:
```bat
taskkill /FI "WINDOWTITLE eq OpenClaw Gateway*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq OpenClaw Proxy*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit Dashboard*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq Cloudflare Tunnel*" >nul 2>&1
wmic process where "name='nginx.exe'" delete >nul 2>&1
wmic process where "name='cloudflared.exe'" delete >nul 2>&1
```

- [ ] **Step 2: Commit**

```bash
git add run_dashboard.bat
git commit -m "fix: update shutdown to kill cloudflared instead of ngrok"
```

---

### Task 8: Verify the final `run_dashboard.bat`

**Files:**
- Read: `run_dashboard.bat`

- [ ] **Step 1: Read the full file and verify structure**

Read `run_dashboard.bat` and confirm:
1. Steps are numbered `[1/10]` through `[10/10]` with no gaps
2. Cloudflared download step exists after nginx download
3. Cloudflared tunnel launch replaces ngrok
4. Status output shows tunnel URL (not ngrok)
5. Shutdown kills cloudflared (not ngrok)
6. No references to `ngrok` remain in the file

- [ ] **Step 2: Fix any issues found**

If any of the above checks fail, edit the file to fix them.

---

## Verification Checklist

After all tasks, confirm:

- [ ] `.gitignore` contains `cloudflared.exe`
- [ ] `ngrok.exe` is no longer tracked by git (`git ls-files ngrok.exe` returns empty)
- [ ] `run_dashboard.bat` has no references to `ngrok`
- [ ] `run_dashboard.bat` steps are numbered `[1/10]` through `[10/10]`
- [ ] Cloudflared download step mirrors nginx download pattern
- [ ] Shutdown section kills `cloudflared.exe` process
- [ ] Status output shows tunnel URL

## First-Time Setup (Manual)

These steps cannot be automated and must be done once per machine:

```bash
cloudflared.exe tunnel login          # Opens browser for Cloudflare auth
cloudflared.exe tunnel create cms-dashboard  # Creates named tunnel, outputs UUID and URL
cloudflared.exe tunnel route dns cms-dashboard <assigned-subdomain>.cfargotunnel.com
```

After this, `run_dashboard.bat` will connect to the tunnel automatically.
