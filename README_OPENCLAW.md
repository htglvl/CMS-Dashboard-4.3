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

## Prerequisites

1. **Node.js 22+** — https://nodejs.org/
2. **OpenClaw** — `npm install -g openclaw@latest`
3. **API key** — Set `XIAOMI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` in `.env`

## Setup

### 1. Install OpenClaw (first time only)

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

The onboarding wizard will guide you through initial configuration.

### 2. Configure the plugin

Edit `~/.openclaw/openclaw.json` and add the CMS Dashboard plugin:

```json5
{
  "plugins": {
    "cms-dashboard": {
      "enabled": true,
      "pythonPath": "python",  // or absolute path to your venv python
      "toolsDir": "D:\\LANCASTER\\UNI\\AI PLACEMENT\\CyberMoor\\CMS Dashboard 4.3\\tools"
    }
  }
}
```

### 3. Start the gateway

```bash
# Option A: Use the batch file
run_openclaw.bat

# Option B: Manual start
openclaw start --plugin ./openclaw-plugin
```

### 4. Open WebChat

Navigate to **http://127.0.0.1:18789/** in your browser.

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

## Architecture

```
User (WebChat) → OpenClaw Gateway → Plugin Tools → Python CLI Scripts → Data/Model
```

- **OpenClaw Gateway**: Routes messages between WebChat and the agent
- **Plugin** (`openclaw-plugin/`): Registers 8 tools, each calling a Python script
- **Python scripts** (`tools/`): CLI wrappers around the existing dashboard data/model
- **Data**: Same CSV files and ML models used by the Streamlit dashboard

## Tool Reference

| Tool | Script | Description |
|------|--------|-------------|
| `query_risk` | `tools/query_risk.py` | Risk predictions by location or district |
| `query_outages` | `tools/query_outages.py` | Historic outage records |
| `get_live_incidents` | `tools/get_live_incidents.py` | Current active incidents |
| `get_recommendations` | `tools/get_recommendations.py` | V2X/chargepoint placement recommendations |
| `query_charging_sites` | `tools/query_charging_sites.py` | Charging site lookups |
| `get_wiki` | `tools/get_wiki.py` | Dashboard documentation |
| `summarize_district` | `tools/summarize_district.py` | Full district analysis |
| `check_new_incidents` | `tools/check_new_incidents.py` | New incident detection with risk context |

## Incident Notifications

The `check_new_incidents` tool tracks seen incidents in `data/.last_incidents_state`. When called, it:
1. Fetches current live incidents from ENW API
2. Compares with previously seen incidents
3. For new incidents, adds risk context (nearest grid cell, nearby chargepoints, historic outages)

To enable automatic notifications, configure a scheduled job in OpenClaw config or call the tool periodically.

## Troubleshooting

- **"Python not found"**: Set `pythonPath` in the plugin config to your venv python path
- **"Tool timeout"**: The recommendation engine can take 30-60s on first run (cached after)
- **"No prediction files"**: Run the dashboard once to generate `models/predictions_*.csv`
