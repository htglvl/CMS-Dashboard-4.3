"""
Automated daily fetcher for historic unplanned outage records from
Electricity North West's OpenDataSoft API.

Uses the dataset EXPORT endpoint (single HTTP request) rather than
paginating through the records API.  A full download of ~309k records
completes in about 60 seconds.

Usage:
    python fetch_outages.py                # Incremental fetch (default)
    python fetch_outages.py --full         # Full re-download of all records
    python fetch_outages.py --since 2024-01-01  # Fetch records since a date
    python fetch_outages.py --output df_cleaned.parquet  # Custom output

Environment:
    Requires ENW_API_KEY in a .env file in the same directory (or a
    parent directory).
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from io import StringIO

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXPORT_URL = "https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets/unplanned-outages/exports/csv"
DEFAULT_OUTPUT = str(Path(__file__).parent / "df_cleaned.csv")
PARQUET_OUTPUT = str(Path(__file__).parent / "df_cleaned.parquet")
STATE_FILE = str(Path(__file__).parent / ".last_fetch_outages")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "fetch_outages.log", encoding="utf-8"),
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
            log.info(f"Last fetch timestamp: {ts}")
            return ts
    return None


def save_last_fetch_date(state_file: Path, iso_date: str) -> None:
    """Persist the ISO date of the most recent record fetched."""
    state_file.write_text(iso_date, encoding="utf-8")
    log.info(f"Saved last fetch timestamp: {iso_date}")


# ---------------------------------------------------------------------------
# Export-based fetcher (single request)
# ---------------------------------------------------------------------------


def fetch_via_export(api_key: str, where: str | None = None) -> pd.DataFrame:
    """Download outage records using the OpenDataSoft export endpoint.

    The export endpoint returns the full dataset (or a filtered subset) as
    a single CSV stream with semicolon delimiters.  This is dramatically
    faster than paginating through the records API (one request vs ~3000).

    Parameters
    ----------
    api_key : str
        OpenDataSoft API key.
    where : str or None
        Optional SQL-like filter (e.g. ``incident_date_time > '2026-01-01'``).

    Returns
    -------
    pd.DataFrame
        Raw outage records with geometry parsed into latitude/longitude.
    """
    params = {
        "limit": -1,          # no limit — get everything
        "apikey": api_key,
    }
    if where:
        params["where"] = where

    log.info(f"Requesting export (where={where or 'all records'})...")
    resp = requests.get(EXPORT_URL, params=params, timeout=300)
    resp.raise_for_status()

    # The export uses semicolons as delimiters and UTF-8 BOM
    raw = resp.content.decode("utf-8-sig")
    df = pd.read_csv(StringIO(raw), sep=";", low_memory=False)
    log.info(f"Downloaded {len(df):,} records ({len(resp.content) / 1_048_576:.1f} MB)")

    # Parse geometry string "lat, lon" into separate columns
    if "geometry" in df.columns:
        coords = df["geometry"].astype(str).str.split(",", n=1, expand=True)
        if coords.shape[1] >= 2:
            df["latitude"] = pd.to_numeric(coords[0].str.strip(), errors="coerce")
            df["longitude"] = pd.to_numeric(coords[1].str.strip(), errors="coerce")
        df.drop(columns=["geometry"], inplace=True)

    return df


# ---------------------------------------------------------------------------
# Merge, derive, save
# ---------------------------------------------------------------------------


def reconcile_with_existing(new_df: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    """Merge new records with any existing output file, deduplicating by reference number.

    After concatenation the datetime columns may contain mixed types (strings
    from the CSV and Timestamps from the new data).  We re-parse them to
    ensure a consistent datetime64 dtype before returning.
    """
    if output_path.exists():
        try:
            existing = pd.read_csv(output_path, encoding="utf-8", low_memory=False)
            log.info(f"Existing file has {len(existing):,} records.")

            # Align dtypes: cast datetime columns in existing data to match new_df
            for col in ["incident_date_time", "restoration_date_time", "Incident Date-time"]:
                if col in new_df.columns and col in existing.columns:
                    existing[col] = pd.to_datetime(existing[col], errors="coerce", utc=True)

            dedup_col = "incident_reference_number"
            if dedup_col in new_df.columns and dedup_col in existing.columns:
                combined = pd.concat([existing, new_df], ignore_index=True)
                before = len(combined)
                combined = combined.drop_duplicates(subset=[dedup_col], keep="last")
                log.info(f"After dedup: {len(combined):,} records (removed {before - len(combined):,} duplicates).")
                return combined
            return pd.concat([existing, new_df], ignore_index=True)
        except Exception as exc:
            log.warning(f"Could not read existing file ({exc}). Using new data only.")
    return new_df


def save_output(df: pd.DataFrame, output_path: Path) -> None:
    """Save the DataFrame to CSV and Parquet."""
    df.to_csv(output_path, index=False, encoding="utf-8")
    # Cast object columns to string to avoid mixed-type parquet errors
    pq_df = df.copy()
    for col in pq_df.select_dtypes(include=["object"]).columns:
        pq_df[col] = pq_df[col].astype(str)
    parquet_path = output_path.with_suffix(".parquet")
    pq_df.to_parquet(parquet_path, index=False)
    log.info(f"Saved {len(df):,} records to {output_path} + {parquet_path}")


# ---------------------------------------------------------------------------
# Derive dashboard-ready fields
# ---------------------------------------------------------------------------


def prepare_for_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns the CMS dashboard expects."""
    if df.empty:
        return df

    df = df.copy()

    # Parse datetimes
    for col in ["incident_date_time", "restoration_date_time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Duration in hours
    if "incident_date_time" in df.columns and "restoration_date_time" in df.columns:
        computed = (df["restoration_date_time"] - df["incident_date_time"]).dt.total_seconds() / 3600.0
        if "incident_duration" in df.columns:
            df["duration-hours"] = computed.fillna(df["incident_duration"] / 60.0)
        else:
            df["duration-hours"] = computed
    elif "incident_duration" in df.columns:
        df["duration-hours"] = df["incident_duration"] / 60.0

    # Temporal fields
    if "incident_date_time" in df.columns:
        try:
            dt_local = df["incident_date_time"].dt.tz_convert("Europe/London")
        except Exception:
            dt_local = df["incident_date_time"]
        df["year"] = dt_local.dt.year
        df["month_name"] = dt_local.dt.month_name()
        df["hour"] = dt_local.dt.hour

        def _month_to_season(month: int) -> str:
            if month in (12, 1, 2):
                return "Winter"
            elif month in (3, 4, 5):
                return "Spring"
            elif month in (6, 7, 8):
                return "Summer"
            return "Autumn"

        df["season"] = dt_local.dt.month.map(lambda m: _month_to_season(m) if pd.notna(m) else None)

    # Duration category
    def _categorise(hours: float) -> str:
        try:
            h = float(hours)
            if h < 3:
                return "x < 3 hours"
            elif h < 6:
                return "3 ≤ x < 6 hours"
            elif h < 12:
                return "6 ≤ x < 12 hours"
            return "x > 12 hours"
        except Exception:
            return None

    if "duration-hours" in df.columns:
        df["duration_category"] = df["duration-hours"].apply(_categorise)

    # Exceptional event flag (always boolean, never NaN)
    if "exceptional_event_id" in df.columns:
        df["is_exceptional_event"] = (
            df["exceptional_event_id"].notna()
            & (df["exceptional_event_id"].astype(str).str.strip() != "")
        ).astype(bool)

    # Dashboard compatibility aliases
    if "incident_date_time" in df.columns:
        df["Incident Date-time"] = df["incident_date_time"]
    if "total_customer_minutes_lost" in df.columns and "Total Customer Minutes Lost" not in df.columns:
        df["Total Customer Minutes Lost"] = df["total_customer_minutes_lost"]

    return df


# ---------------------------------------------------------------------------
# Internal helpers & main fetch entry point
# ---------------------------------------------------------------------------


def _get_local_latest(output_path: Path) -> str | None:
    """Read the most recent incident_date_time from the local CSV file."""
    if not output_path.exists():
        return None
    try:
        # Only read the one column to keep it fast
        col = pd.read_csv(output_path, usecols=["incident_date_time"], encoding="utf-8")
        col["incident_date_time"] = pd.to_datetime(col["incident_date_time"], errors="coerce", utc=True)
        latest = col["incident_date_time"].max()
        if pd.notna(latest):
            return str(latest)
    except Exception:
        pass
    return None


def run_daily_fetch(
    output_filename: str = DEFAULT_OUTPUT,
    full: bool = False,
    since: str | None = None,
) -> dict:
    """Run the daily fetch and return a summary dict.

    Compares the local file's latest record with the API to determine
    exactly what's missing.  For full downloads the file is replaced;
    for incremental fetches new records are appended and deduplicated.

    Returns
    -------
    dict
        Keys: fetched, new_total, saved_to, skipped (bool), error (str or None).
    """
    base_dir = Path(__file__).parent
    output_path = base_dir / output_filename
    state_file = base_dir / STATE_FILE
    result = {"fetched": 0, "new_total": 0, "saved_to": str(output_path), "skipped": False, "error": None}

    try:
        api_key = load_api_key()
    except SystemExit:
        result["error"] = "ENW_API_KEY not configured"
        return result

    # Determine the starting point for the fetch
    where_clause = None

    if since:
        # User explicitly asked for records since a date
        where_clause = f"incident_date_time >= '{since}'"
    elif not full:
        # Smart gap detection: use the later of (state file, local file)
        state_ts = load_last_fetch_date(state_file)
        local_ts = _get_local_latest(output_path)
        candidates = [ts for ts in [state_ts, local_ts] if ts]
        if candidates:
            best_ts = max(candidates)
            where_clause = f"incident_date_time > '{best_ts}'"
            log.info(f"Local latest: {local_ts or 'N/A'} | State: {state_ts or 'N/A'}")
            log.info(f"Fetching records after: {best_ts}")
        else:
            log.info("No local data or state file found. Performing full download.")
    else:
        log.info("Full download requested.")

    # Fetch from the API
    try:
        df = fetch_via_export(api_key, where=where_clause)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    if df.empty:
        # No new records — DO NOT update the state file with "now".
        # Preserving the real last-data timestamp keeps the gap-detection
        # working for the next run.  Just touch it if it doesn't exist yet
        # so a missing state file doesn't force repeated full downloads.
        result["skipped"] = True
        if not state_file.exists():
            save_last_fetch_date(state_file, datetime.now(timezone.utc).isoformat())
        return result

    df = prepare_for_dashboard(df)

    # For full downloads or first run, replace the file; for incremental, merge
    if full or not output_path.exists():
        save_output(df, output_path)
        result["new_total"] = len(df)
    else:
        df = reconcile_with_existing(df, output_path)
        save_output(df, output_path)
        result["new_total"] = len(df)

    result["fetched"] = len(df)

    # Invalidate caches so the dashboard recomputes with new data
    try:
        from advanced_charts.data import invalidate_cache
        invalidate_cache()
    except ImportError:
        pass
    try:
        from advanced_charts.risk_model import invalidate_features_cache
        invalidate_features_cache()
    except ImportError:
        pass
    try:
        from advanced_charts.recommendation_engine import invalidate_report_cache
        invalidate_report_cache()
    except ImportError:
        pass
    try:
        from advanced_charts.charts import invalidate_chart_data_cache
        invalidate_chart_data_cache()
    except ImportError:
        pass
    try:
        pred_cache = Path(__file__).parent / "risk_predictions_cache.pkl"
        if pred_cache.exists():
            pred_cache.unlink()
    except Exception:
        pass

    # Update state file with the most recent incident timestamp from the data.
    # Re-parse the column to ensure consistent datetime64 dtype (the merge
    # with an existing CSV can introduce mixed float/Timestamp values).
    if "incident_date_time" in df.columns:
        dt_col = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)
        latest = dt_col.max()
        if pd.notna(latest):
            save_last_fetch_date(state_file, str(latest))
    else:
        save_last_fetch_date(state_file, datetime.now(timezone.utc).isoformat())

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Fetch historic unplanned outage records from ENW OpenDataSoft API."
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Full re-download of all records (ignores last fetch date).",
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Fetch records since this ISO date (e.g. 2024-01-01). Overrides state file.",
    )
    parser.add_argument(
        "--output", type=str, default=DEFAULT_OUTPUT,
        help=f"Output filename (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("ENW Unplanned Outages — Daily Fetch")
    log.info("=" * 60)

    result = run_daily_fetch(
        output_filename=args.output,
        full=args.full,
        since=args.since,
    )

    if result["error"]:
        log.error(f"Fetch failed: {result['error']}")
    elif result["skipped"]:
        log.info("No new records found. Nothing to save.")
    else:
        log.info(f"Fetched {result['fetched']:,} records. Total in file: {result['new_total']:,}")

    log.info("Fetch complete.")


if __name__ == "__main__":
    main()
