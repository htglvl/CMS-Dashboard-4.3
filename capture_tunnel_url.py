"""Capture Cloudflare tunnel URL with auto-restart.

Starts cloudflared, captures the trycloudflare.com URL, saves it to
tunnel_url.txt, copies to clipboard, and updates Cloudflare Workers KV.

Restarts every RESTART_INTERVAL (12h) or on failure.  The permanent
redirect at https://cms.cms-tunnel-redirect.workers.dev/ always points
to the latest tunnel URL via KV.
"""

import os
import re
import sys
import time
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

MAX_RESTARTS = 10               # restart cap before giving up
RESTART_DELAY = 5               # seconds between restarts
RESTART_INTERVAL = 12 * 3600    # 12 hours in seconds
HEALTH_CHECK_INTERVAL = 120     # seconds between health pings
HEALTH_CHECK_TIMEOUT = 10       # seconds to wait for a response

def update_cloudflare_kv(url):
    """Push the new tunnel URL to Cloudflare Workers KV."""
    token = os.environ.get("CF_API_TOKEN")
    account_id = os.environ.get("CF_ACCOUNT_ID")
    namespace_id = os.environ.get("CF_KV_NAMESPACE_ID")

    if not all([token, account_id, namespace_id]):
        print("Cloudflare KV env vars not set, skipping.", file=sys.stderr)
        return

    try:
        resp = requests.put(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/storage/kv/namespaces/{namespace_id}/values/tunnel_url",
            headers={"Authorization": f"Bearer {token}"},
            data=url.encode(),
            timeout=10,
        )
        if resp.status_code == 200:
            print("Updated Cloudflare KV with new tunnel URL.", file=sys.stderr)
        else:
            print(f"Cloudflare KV update failed ({resp.status_code}): {resp.text}", file=sys.stderr)
    except Exception as e:
        print(f"Failed to update Cloudflare KV: {e}", file=sys.stderr)

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
    """Persist the URL and push to Cloudflare KV."""
    with open("tunnel_url.txt", "w") as f:
        f.write(url)

    subprocess.run(["clip"], input=url.encode(), check=True)

    print(f"\nTunnel URL: {url}", file=sys.stderr)
    print(f"Saved to: tunnel_url.txt", file=sys.stderr)
    print(f"Copied to clipboard!", file=sys.stderr)
    update_cloudflare_kv(url)

def run_tunnel():
    """Main loop: start tunnel, monitor, restart every 12h or on failure."""
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

        # Monitor loop — health check + scheduled 12h restart
        last_health = time.time()
        started_at = time.time()
        while True:
            # 1. Has the process exited?
            if proc.poll() is not None:
                print(f"\ncloudflared exited (code {proc.returncode}).", file=sys.stderr)
                break

            # 2. Scheduled restart every 12 hours
            if time.time() - started_at >= RESTART_INTERVAL:
                print(f"\n12-hour restart reached. Cycling tunnel...", file=sys.stderr)
                proc.kill()
                break

            # 3. Periodic health check
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
