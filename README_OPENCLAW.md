# OpenClaw Integration for CMS Dashboard

This guide explains how to set up OpenClaw to chat with the CMS Dashboard's data, risk model, and wiki.

## What You Get

An AI agent accessible via WebChat that can:
- **Query risk predictions**: "Which areas have the highest outage risk?"
- **Search outage history**: "Show me outages in Lancaster from 2023"
- **Check live incidents**: "Are there any active power cuts right now?"
- **Get placement recommendations**: "Where should we put new V2X chargepoints?"
- **Look up charging sites**: "Find all V2X sites near Lancaster"
- **Explain dashboard features**: "What does the radar chart show?"
- **Summarize districts**: "Give me a full analysis of Preston"
- **Auto-notify on new incidents**: Alerts with risk context and nearby infrastructure

---

## Prerequisites

- **Node.js 22+** — https://nodejs.org/
- **OpenClaw** — `npm install -g openclaw@latest`
- **Python 3.12+** — with venv activated
- **API key** — Set `XIAOMI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` in `.env`

---

## Quick Setup (Automated)

```bash
setup.bat
```

This will:
1. ✅ Build the OpenClaw plugin
2. ✅ Check if OpenClaw is installed
3. ✅ Run `openclaw onboard` if first time
4. ✅ Auto-configure `~/.openclaw/openclaw.json` with:
   - Gateway settings (port 18789, loopback, no auth)
   - CMS Dashboard plugin (pythonPath, toolsDir)

Then start everything:

```bash
run_dashboard.bat
```

Open **http://127.0.0.1:18789/** for WebChat.

---

## Manual Setup

If you prefer to configure manually:

### 1. Install OpenClaw

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

### 2. Edit config

Edit `~/.openclaw/openclaw.json`:

```json
{
  "gateway": {
    "mode": "local",
    "auth": {
      "mode": "none"
    },
    "port": 18789,
    "bind": "loopback",
    "controlUi": {
      "allowInsecureAuth": true,
      "allowedOrigins": ["*"]
    }
  },
  "plugins": {
    "entries": {
      "cms-dashboard": {
        "enabled": true,
        "pythonPath": "C:\\path\\to\\CMS Dashboard 4.3\\venv\\Scripts\\python.exe",
        "toolsDir": "C:\\path\\to\\CMS Dashboard 4.3\\tools"
      }
    }
  }
}
```

### 3. Start

```bash
run_dashboard.bat
```

---

## Example Questions

| Question | Tools Used |
|----------|-----------|
| "Which local authorities are at highest outage risk?" | `query_risk` |
| "Show me outages in Bolton from 2024" | `query_outages` |
| "Are there any active power cuts?" | `get_live_incidents` |
| "Where should we put new V2X chargepoints?" | `get_recommendations` |
| "Find V2X sites near Lancaster" | `query_charging_sites` |
| "What does the radar chart show?" | `get_wiki` |
| "Give me a full analysis of Preston" | `summarize_district` |

---

## Architecture

```
User (WebChat) → OpenClaw Gateway → Plugin Tools → Python CLI Scripts → Data/Model
```

- **OpenClaw Gateway** (port 18789): Routes messages between WebChat and the agent
- **Plugin** (`openclaw-plugin/`): Registers 9 tools, each calling a Python script
- **Python scripts** (`tools/`): CLI wrappers around the existing dashboard data/model
- **Data**: Same CSV files and ML models used by the Streamlit dashboard

---

## Tool Reference

| Tool | Script | Description |
|------|--------|-------------|
| `geocode` | `tools/geocode.py` | Convert place names to lat/lon coordinates |
| `query_risk` | `tools/query_risk.py` | Risk predictions by location or district |
| `query_outages` | `tools/query_outages.py` | Historic outage records |
| `get_live_incidents` | `tools/get_live_incidents.py` | Current active incidents |
| `get_recommendations` | `tools/get_recommendations.py` | V2X/chargepoint placement recommendations |
| `query_charging_sites` | `tools/query_charging_sites.py` | Charging site lookups |
| `get_wiki` | `tools/get_wiki.py` | Dashboard documentation |
| `summarize_district` | `tools/summarize_district.py` | Full district analysis |
| `check_new_incidents` | `tools/check_new_incidents.py` | New incident detection with risk context |

See `tools/README.md` for detailed usage of each tool.

---

## Skills

The OpenClaw plugin includes AI workflow skills in `openclaw-plugin/skills/`:

| Skill | Description |
|-------|-------------|
| `risk-analysis` | Workflow for analyzing risk at locations |
| `documentation` | Access dashboard wiki and documentation |

These skills guide the AI on how to use the tools effectively.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Python not found" | Run `setup.bat` again — it auto-configures the pythonPath |
| "Tool timeout" | The recommendation engine can take 30-60s on first run (cached after) |
| "No prediction files" | Run `python advanced_charts/risk_model.py` to generate models |
| "OpenClaw command not found" | Run `npm install -g openclaw@latest` |
| "Plugin not loading" | Check `openclaw-plugin/dist/index.js` exists (run `setup.bat`) |
| "Gateway won't start" | Check if port 18789 is in use: `netstat -ano | findstr :18789` |
