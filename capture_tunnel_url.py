"""Capture Cloudflare tunnel URL with auto-restart.

Starts cloudflared, captures the trycloudflare.com URL, saves it to
tunnel_url.txt, copies to clipboard, and sends via ntfy.sh.

Monitors the process and restarts automatically if it exits or becomes
unresponsive (health check every HEALTH_CHECK_INTERVAL seconds).
"""

import re
import sys
import time
import subprocess
import requests

NTFY_TOPIC = "cms-dashboard-tunnel"
MAX_RESTARTS = 10               # restart cap before giving up
RESTART_DELAY = 5               # seconds between restarts
HEALTH_CHECK_INTERVAL = 120     # seconds between health pings
HEALTH_CHECK_TIMEOUT = 10       # seconds to wait for a response

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

def start_cloudflared():
    """Spawn a cloudflared quick-tunnel process."""
    return subprocess.Popen(
        ["cloudflared.exe", "tunnel", "--url", "http://localhost:8501"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

def wait_for_url(proc, timeout=30):
    """Read cloudflared output until a trycloudflare.com URL appears."""
    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            # Process exited before producing a URL
            if proc.poll() is not None:
                return None
            time.sleep(0.5)
            continue

        print(line, end="", file=sys.stderr)
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if match:
            return match.group(0)
    return None

def health_check(url):
    """Ping the tunnel URL; return True if reachable."""
    try:
        r = requests.get(url, timeout=HEALTH_CHECK_TIMEOUT, allow_redirects=False)
        # Any response (even 502/503) means the tunnel edge is alive
        return r.status_code < 500
    except requests.RequestException:
        return False

def save_and_notify(url):
    """Persist the URL and broadcast it."""
    with open("tunnel_url.txt", "w") as f:
        f.write(url)

    subprocess.run(["clip"], input=url.encode(), check=True)

    print(f"\nTunnel URL: {url}", file=sys.stderr)
    print(f"Saved to: tunnel_url.txt", file=sys.stderr)
    print(f"Copied to clipboard!", file=sys.stderr)
    send_notification(url)

def run_tunnel():
    """Main loop: start tunnel, monitor, auto-restart on failure."""
    restarts = 0

    while restarts < MAX_RESTARTS:
        if restarts > 0:
            print(f"\nRestarting tunnel (attempt {restarts}/{MAX_RESTARTS})...", file=sys.stderr)

        proc = start_cloudflared()
        url = wait_for_url(proc)

        if not url:
            print("Failed to capture URL. Retrying...", file=sys.stderr)
            proc.kill()
            restarts += 1
            time.sleep(RESTART_DELAY)
            continue

        save_and_notify(url)
        restarts = 0  # reset on successful start

        # Monitor loop — check process liveness + periodic health ping
        last_health = time.time()
        while True:
            # 1. Has the process exited?
            if proc.poll() is not None:
                print(f"\ncloudflared exited (code {proc.returncode}).", file=sys.stderr)
                break

            # 2. Periodic health check
            if time.time() - last_health >= HEALTH_CHECK_INTERVAL:
                if not health_check(url):
                    print(f"\nHealth check failed for {url}. Restarting...", file=sys.stderr)
                    proc.kill()
                    break
                last_health = time.time()

            time.sleep(5)

        restarts += 1
        time.sleep(RESTART_DELAY)

    print(f"\nExceeded {MAX_RESTARTS} restarts. Giving up.", file=sys.stderr)

if __name__ == "__main__":
    run_tunnel()
