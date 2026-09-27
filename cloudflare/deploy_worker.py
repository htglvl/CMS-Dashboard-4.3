"""Deploy the dashboard proxy using the existing .env Cloudflare credentials."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import tomllib

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_URL_FILE = ROOT / "worker_url.txt"


def deploy():
    load_dotenv(ROOT / ".env")
    PUBLIC_URL_FILE.unlink(missing_ok=True)
    config = tomllib.loads((ROOT / "cloudflare/wrangler.toml").read_text())
    required = ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_KV_NAMESPACE_ID")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Set these values in .env: " + ", ".join(missing))
    namespace = os.environ["CF_KV_NAMESPACE_ID"]
    configured = next(item["id"] for item in config["kv_namespaces"] if item["binding"] == "TUNNEL_KV")
    if namespace != configured:
        raise RuntimeError("CF_KV_NAMESPACE_ID must match TUNNEL_KV in cloudflare/wrangler.toml.")

    base = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}"
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {os.environ['CF_API_TOKEN']}"

    def api(method, path, **kwargs):
        response = session.request(method, base + path, timeout=90, **kwargs)
        try:
            body = response.json()
        except ValueError:
            raise RuntimeError(f"Cloudflare returned HTTP {response.status_code} without a JSON response.") from None
        if not response.ok or not body.get("success"):
            # Do not print request headers or credentials.
            errors = "; ".join(str(error.get("code", "unknown")) for error in body.get("errors", []))
            raise RuntimeError(
                f"Cloudflare {method} {path} failed (HTTP {response.status_code}; codes: {errors}). "
                "Check account ID and token permissions: Workers Scripts Edit and Workers KV Storage Edit."
            )
        return body.get("result")

    subdomain = api("GET", "/workers/subdomain").get("subdomain")
    if not subdomain:
        raise RuntimeError("Create a workers.dev subdomain in the Cloudflare dashboard first.")
    name = config["name"]
    main = config["main"]
    metadata = {
        "main_module": main,
        "compatibility_date": config["compatibility_date"],
        "bindings": [{"type": "kv_namespace", "name": "TUNNEL_KV", "namespace_id": namespace}],
    }
    print(f"Deploying Cloudflare Worker '{name}'...", flush=True)
    api("PUT", f"/workers/scripts/{name}", files={
        "metadata": (None, json.dumps(metadata), "application/json"),
        main: (main, (ROOT / "cloudflare" / main).read_bytes(), "application/javascript+module"),
    })
    api("POST", f"/workers/scripts/{name}/subdomain", json={"enabled": True})
    public_url = f"https://{name}.{subdomain}.workers.dev"
    PUBLIC_URL_FILE.write_text(public_url, encoding="utf-8")
    print(f"Permanent dashboard address: {public_url}", flush=True)


def wait_until_ready(timeout=120):
    public_url = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip()
    deadline = time.monotonic() + timeout
    print("Waiting for the dashboard through the permanent Worker address...", flush=True)
    while time.monotonic() < deadline:
        try:
            response = requests.get(public_url + "/_stcore/health", timeout=10, allow_redirects=False)
            if response.status_code == 200 and response.text.strip() == "ok":
                print(f"Ready. Share and bookmark: {public_url}", flush=True)
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    raise RuntimeError("Public dashboard did not become ready within 120 seconds. Check logs/cloudflare-tunnel.log and local services.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", action="store_true", help="Wait for the deployed proxy and tunnel to serve Streamlit.")
    args = parser.parse_args()
    try:
        wait_until_ready() if args.wait else deploy()
    except (RuntimeError, requests.RequestException, OSError, ValueError, StopIteration) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
