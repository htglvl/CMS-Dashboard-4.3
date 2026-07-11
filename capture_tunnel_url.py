"""Capture Cloudflare tunnel URL and send notification.

Reads cloudflared output, extracts the trycloudflare.com URL,
saves it to tunnel_url.txt, copies to clipboard, and sends via ntfy.sh.
"""

import re
import sys
import time
import subprocess
import requests

NTFY_TOPIC = "cms-dashboard-tunnel"

def send_notification(url):
    """Send URL via ntfy.sh (free, no login needed)."""
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=f"CMS Dashboard Tunnel URL:\n{url}".encode(),
            headers={"Title": "CMS Dashboard URL"}
        )
        print(f"Notification sent to ntfy.sh/{NTFY_TOPIC}", file=sys.stderr)
    except Exception as e:
        print(f"Failed to send notification: {e}", file=sys.stderr)

def capture_url():
    """Start cloudflared, capture URL, save to file."""
    print("Starting Cloudflare tunnel...", file=sys.stderr)
    
    # Start cloudflared
    proc = subprocess.Popen(
        ["cloudflared.exe", "tunnel", "--url", "http://localhost:8501"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    url = None
    start = time.time()
    
    # Wait up to 30 seconds for URL
    while time.time() - start < 30:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.5)
            continue
        
        print(line, end="", file=sys.stderr)
        
        # Look for trycloudflare.com URL
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if match:
            url = match.group(0)
            break
    
    if url:
        # Save to file
        with open("tunnel_url.txt", "w") as f:
            f.write(url)
        
        # Copy to clipboard (Windows)
        subprocess.run(["clip"], input=url.encode(), check=True)
        
        print(f"\nTunnel URL: {url}", file=sys.stderr)
        print(f"Saved to: tunnel_url.txt", file=sys.stderr)
        print(f"Copied to clipboard!", file=sys.stderr)
        
        # Send notification
        send_notification(url)
    else:
        print("\nFailed to capture URL within 30 seconds", file=sys.stderr)
    
    # Keep cloudflared running
    proc.wait()

if __name__ == "__main__":
    capture_url()
