"""Fetch current live incidents from the ENW OpenDataSoft API.

Usage::

    from fetch_live_incidents import fetch_live_incidents
    df = fetch_live_incidents()

The dataset requires an API key set via ``ENW_API_KEY`` in the environment
or ``.env`` file.
"""

import logging
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

LIVE_INCIDENTS_URL = (
    "https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/"
    "catalog/datasets/live_incidents/exports/json"
)


def _load_api_key() -> str | None:
    """Load the ENW API key. Returns None if not configured."""
    import os
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
    return api_key if api_key else None


def fetch_live_incidents(api_key: str | None = None) -> pd.DataFrame:
    """Fetch current live incidents from the ENW OpenDataSoft API.

    Parameters
    ----------
    api_key : str, optional
        OpenDataSoft API key.  If ``None`` the key is read from the
        ``ENW_API_KEY`` environment variable.

    Returns
    -------
    pd.DataFrame
        Columns: incident_num, incident_type, outage_time,
        customers_affected, customers_off_supply, incident_status,
        estimated_restoration_time, latitude, longitude.

        Returns an empty DataFrame if there are no active incidents
        or the request fails.
    """
    columns = [
        "incident_num", "incident_type", "outage_time",
        "customers_affected", "customers_off_supply",
        "incident_status", "estimated_restoration_time",
        "latitude", "longitude",
    ]
    empty = pd.DataFrame(columns=columns)

    if api_key is None:
        api_key = _load_api_key()
    if not api_key:
        log.warning("ENW_API_KEY not set – cannot fetch live incidents")
        return empty

    try:
        resp = requests.get(
            LIVE_INCIDENTS_URL,
            params={"apikey": api_key},
            timeout=15,
        )
        log.info("Live incidents API status: %s, length: %d", resp.status_code, len(resp.text))
        resp.raise_for_status()
        data = resp.json()
        log.info("Live incidents records: %d", len(data) if isinstance(data, list) else -1)
    except Exception as exc:
        log.warning("Live incidents fetch failed: %s", exc)
        return empty

    if not data:
        log.info("Live incidents: API returned empty data")
        return empty

    df = pd.DataFrame(data)

    # Normalise column names to lowercase (API sometimes returns mixed case)
    df.columns = [c.lower() for c in df.columns]

    # Flatten geo_point_2d into latitude / longitude
    if "geo_point_2d" in df.columns:
        def _parse_geo(val):
            if isinstance(val, dict):
                return val.get("lat"), val.get("lon")
            if isinstance(val, str) and "," in val:
                parts = val.split(",")
                return float(parts[0].strip()), float(parts[1].strip())
            return None, None

        df[["latitude", "longitude"]] = df["geo_point_2d"].apply(
            lambda p: pd.Series(_parse_geo(p))
        )
        df.drop(columns=["geo_point_2d"], inplace=True)

    # Drop geo_shape (not needed for display)
    df.drop(columns=["geo_shape"], errors="ignore", inplace=True)

    # Parse datetime columns
    for col in ("outage_time", "estimated_restoration_time"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    return df
