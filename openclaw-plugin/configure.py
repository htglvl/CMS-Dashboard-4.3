"""
Configure OpenClaw to use the CMS Dashboard plugin.
Run this script to automatically update ~/.openclaw/openclaw.json

Also syncs the CMS API provider (Xiaomi MiMo billing, pay-as-you-go) from
the repo .env — CMS_API_BASE_URL / CMS_API_KEY / CMS_API_MODEL replace the
retired monthly XIAOMI_API_KEY token-plan setup. Edit .env and re-run this
script (run_dashboard.bat does it on every start) to change endpoints/keys.
"""

import json
import os
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"

# Model catalogue mirrored from the previous xiaomi-token-plan provider entry.
CMS_MODELS = [
    {
        "id": "mimo-v2.5-pro",
        "name": "Xiaomi MiMo V2.5 Pro",
        "reasoning": True,
        "input": ["text"],
        "cost": {
            "input": 1,
            "output": 3,
            "cacheRead": 0.2,
            "cacheWrite": 0,
            "tieredPricing": [
                {"input": 1, "output": 3, "cacheRead": 0.2, "cacheWrite": 0, "range": [0, 256000]},
                {"input": 1, "output": 3, "cacheRead": 0.4, "cacheWrite": 0, "range": [256000]},
            ],
        },
        "contextWindow": 1048576,
        "maxTokens": 32000,
    },
    {
        "id": "mimo-v2.5",
        "name": "Xiaomi MiMo V2.5",
        "reasoning": True,
        "input": ["text", "image"],
        "cost": {
            "input": 0.4,
            "output": 2,
            "cacheRead": 0.08,
            "cacheWrite": 0,
            "tieredPricing": [
                {"input": 0.4, "output": 2, "cacheRead": 0.08, "cacheWrite": 0, "range": [0, 256000]},
                {"input": 0.4, "output": 2, "cacheRead": 0.16, "cacheWrite": 0, "range": [256000]},
            ],
        },
        "contextWindow": 1048576,
        "maxTokens": 32000,
    },
]


def load_env():
    """Load the repo .env (same fallback approach as data/fetch_*.py)."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sync_cms_api(config):
    """Point OpenClaw at the CMS API provider using values from .env."""
    base_url = os.environ.get("CMS_API_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
    api_key = os.environ.get("CMS_API_KEY", "").strip()

    models_cfg = config.setdefault("models", {})
    models_cfg.setdefault("mode", "merge")
    providers = models_cfg.setdefault("providers", {})
    # Retire the monthly token-plan provider entirely
    providers.pop("xiaomi-token-plan", None)
    providers["cms-api"] = {
        "baseUrl": base_url,
        "api": "openai-completions",
        "apiKey": api_key,
        "models": CMS_MODELS,
    }

    defaults = config.setdefault("agents", {}).setdefault("defaults", {})
    defaults["models"] = {
        "cms-api/mimo-v2.5-pro": {"alias": "Xiaomi MiMo V2.5 Pro"},
        "cms-api/mimo-v2.5": {},
    }
    defaults["model"] = {"primary": "cms-api/mimo-v2.5"}

    profiles = config.setdefault("auth", {}).setdefault("profiles", {})
    profiles.pop("xiaomi-token-plan:default", None)
    profiles["cms-api:default"] = {"provider": "cms-api", "mode": "api_key"}

    if not api_key:
        print("WARNING: CMS_API_KEY is empty in .env - the agent will have no LLM access")

    return base_url


def main():
    load_env()
    config_path = os.path.expanduser(r'~\.openclaw\openclaw.json')

    # Read existing config or create new
    if os.path.exists(config_path):
        shutil.copy2(config_path, config_path + '.bak.configure')
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        config = {}

    # Ensure structure exists
    if 'gateway' not in config:
        config['gateway'] = {
            "mode": "local",
            "auth": {"mode": "none"},
            "port": 18789,
            "bind": "loopback",
            "controlUi": {
                "allowInsecureAuth": True,
                "allowedOrigins": ["*"]
            }
        }

    if 'plugins' not in config:
        config['plugins'] = {}

    if 'entries' not in config['plugins']:
        config['plugins']['entries'] = {}

    # Update CMS Dashboard plugin entry.
    # NOTE: this OpenClaw version's schema only accepts {enabled: bool} here —
    # older pythonPath/toolsDir fields fail config validation and block startup,
    # so overwrite the entry instead of preserving stale keys.
    config['plugins']['entries']['cms-dashboard'] = {"enabled": True}

    # Sync CMS API provider settings from .env
    base_url = sync_cms_api(config)

    # Write updated config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"OpenClaw config updated: {config_path}")
    print(f"  CMS API:   {base_url} (model: mimo-v2.5)")


if __name__ == "__main__":
    main()
