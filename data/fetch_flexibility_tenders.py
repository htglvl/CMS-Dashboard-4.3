"""
Automated fetcher for flexibility tender site requirements from
Electricity North West's OpenDataSoft API.

Downloads the full GeoJSON dataset and saves it to
``data/flexibility_tenders.geojson``.  Uses a state file to skip
fetches when the data was refreshed within the last 3 months.

Usage:
    python fetch_flexibility_tenders.py            # Fetch if stale (>3 months)
    python fetch_flexibility_tenders.py --full     # Force re-download
    python fetch_flexibility_tenders.py --check    # Check staleness only

Environment:
    Requires ENW_API_KEY in a .env file in the project root.
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPORT_URL = (
    "https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/"
    "datasets/enwl-flexibility-tender-site-requirements/exports/geojson"
)
DEFAULT_OUTPUT = str(Path(__file__).parent / "flexibility_tenders.geojson")
STATE_FILE = str(Path(__file__).parent / ".last_fetch_flexibility")

# Refresh cycle: 3 months (90 days)
REFRESH_DAYS = 90

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "fetch_flexibility.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_api_key() -> str:
    """Load the ENW API key from a .env file or environment variable."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / ".env"

    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    api_key = os.environ.get("ENW_API_KEY", "").strip()
    if not api_key:
        log.error("ENW_API_KEY not found. Set it in .env or as an environment variable.")
        sys.exit(1)
    return api_key


def load_last_fetch_date(state_file: Path) -> str | None:
    """Read the ISO date of the last successful fetch from the state file."""
    if state_file.exists():
        ts = state_file.read_text(encoding="utf-8").strip()
        if ts:
            log.info(f"Last flexibility fetch timestamp: {ts}")
            return ts
    return None


def save_last_fetch_date(state_file: Path, iso_date: str) -> None:
    """Persist the ISO date of the most recent fetch."""
    state_file.write_text(iso_date, encoding="utf-8")
    log.info(f"Saved flexibility fetch timestamp: {iso_date}")


def is_fetch_needed(state_file: Path) -> bool:
    """Return True if the data is stale (>REFRESH_DAYS) or never fetched."""
    last_ts = load_last_fetch_date(state_file)
    if last_ts is None:
        return True
    try:
        last_dt = datetime.fromisoformat(last_ts)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_dt
        if age > timedelta(days=REFRESH_DAYS):
            log.info(f"Flexibility data is {age.days} days old (>{REFRESH_DAYS} days). Refresh needed.")
            return True
        log.info(f"Flexibility data is {age.days} days old. Still fresh.")
        return False
    except ValueError:
        log.warning(f"Could not parse last fetch date: {last_ts}. Will re-fetch.")
        return True


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


def fetch_flexibility_geojson(api_key: str) -> str | None:
    """Download the full flexibility tender GeoJSON from the API.

    Returns the raw GeoJSON string, or None on failure.
    """
    params = {"limit": -1, "apikey": api_key}

    log.info("Requesting flexibility tenders GeoJSON export...")
    try:
        resp = requests.get(EXPORT_URL, params=params, timeout=300)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("API request failed: %s", exc)
        return None

    content = resp.content.decode("utf-8-sig")

    # Basic validation: should start with GeoJSON structure
    stripped = content.lstrip()
    if not stripped.startswith("{"):
        log.error("Response is not valid GeoJSON (starts with %r)", stripped[:50])
        return None

    log.info("Downloaded flexibility tenders (%.1f KB)", len(resp.content) / 1024)
    return content


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_flexibility_fetch(
    output_path: str = DEFAULT_OUTPUT,
    full: bool = False,
    check_only: bool = False,
) -> dict:
    """Fetch flexibility tenders and return a summary dict.

    Returns
    -------
    dict
        Keys: fetched (bool), saved_to, skipped (bool), error (str or None).
    """
    out_path = Path(output_path)
    state_file = Path(STATE_FILE)
    result = {"fetched": False, "saved_to": str(out_path), "skipped": False, "error": None}

    if check_only:
        needed = is_fetch_needed(state_file)
        result["skipped"] = not needed
        if needed:
            log.info("Flexibility data needs refresh.")
        else:
            log.info("Flexibility data is still fresh.")
        return result

    # Check if fetch is needed (unless --full)
    if not full and not is_fetch_needed(state_file):
        result["skipped"] = True
        log.info("Skipping flexibility fetch — data is fresh.")
        return result

    try:
        api_key = load_api_key()
    except SystemExit:
        result["error"] = "ENW_API_KEY not configured"
        # Fall back to existing file if available
        if out_path.exists():
            log.warning("API key missing but existing file found at %s — keeping it.", out_path)
        return result

    geojson_str = fetch_flexibility_geojson(api_key)

    if geojson_str is None:
        result["error"] = "Failed to fetch flexibility tenders from API"
        # Keep existing file — don't delete it on failure
        if out_path.exists():
            log.warning("API fetch failed but existing file found — keeping it.")
        return result

    # Save to disk
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(geojson_str, encoding="utf-8")
    log.info("Saved flexibility tenders to %s", out_path)

    result["fetched"] = True
    save_last_fetch_date(state_file, datetime.now(timezone.utc).isoformat())

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Fetch flexibility tender site requirements from ENW OpenDataSoft API."
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Force re-download regardless of last fetch date.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check if data is stale without fetching.",
    )
    parser.add_argument(
        "--output", type=str, default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("ENW Flexibility Tenders — Fetch")
    log.info("=" * 60)

    result = run_flexibility_fetch(
        output_path=args.output,
        full=args.full,
        check_only=args.check,
    )

    if result["error"]:
        log.error(f"Fetch failed: {result['error']}")
    elif result["skipped"]:
        log.info("Data is still fresh. Nothing to do.")
    elif result["fetched"]:
        log.info("Flexibility tenders saved to %s", result["saved_to"])

    log.info("Done.")


if __name__ == "__main__":
    main()
