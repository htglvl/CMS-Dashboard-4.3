"""
Configure OpenClaw to use the CMS Dashboard plugin.
Run this script to automatically update ~/.openclaw/openclaw.json
"""

import json
import os
import sys

def main():
    config_path = os.path.expanduser(r'~\.openclaw\openclaw.json')
    
    # Get project root (parent of openclaw-plugin directory)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    python_path = os.path.join(project_root, 'venv', 'Scripts', 'python.exe')
    tools_dir = os.path.join(project_root, 'tools')
    
    # Read existing config or create new
    if os.path.exists(config_path):
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
    
    # Update CMS Dashboard plugin
    config['plugins']['entries']['cms-dashboard'] = {
        "enabled": True,
        "pythonPath": python_path,
        "toolsDir": tools_dir
    }
    
    # Write updated config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"OpenClaw config updated: {config_path}")
    print(f"  pythonPath: {python_path}")
    print(f"  toolsDir: {tools_dir}")

if __name__ == "__main__":
    main()
