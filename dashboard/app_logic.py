"""Application logic — data loading, risk model computation, filtering.

All functions here are pure data operations with no Streamlit UI calls.
"""

import json
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from data.fetch_live_incidents import fetch_live_incidents
from dashboard.sidebar import apply_filters


# ── Data loading ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data(outage_file, site_file, _outage_mtime=0, _site_mtime=0):
    """Load and cache selected outages and site datasets. Stays in RAM until Streamlit restarts."""
    try:
        charging_sites = pd.read_csv(site_file, low_memory=False)
        if outage_file.lower().endswith('.parquet'):
            outages = pd.read_parquet(outage_file)
        else:
            outages = pd.read_csv(outage_file, low_memory=False)
        if 'hour' not in outages.columns:
            if 'start_time' in outages.columns:
                outages['hour'] = pd.to_datetime(outages['start_time'], errors='coerce').dt.hour
            elif 'Incident Date-time' in outages.columns:
                outages['hour'] = pd.to_datetime(outages['Incident Date-time'], errors='coerce').dt.hour
            else:
                outages['hour'] = 0
        return charging_sites, outages
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None


# ── Flexibility tenders (cached) ─────────────────────────────────────────

@st.cache_data
def load_flexibility_tenders(geojson_path: str, _file_mtime: float = 0):
    """Load flexibility tender polygons from GeoJSON.

    Returns
    -------
    tuple or None
        (gdf, grouped_dict) where:
        - gdf: GeoDataFrame with one row per unique substation (dissolved geometry)
        - grouped_dict: {substation_name: [list of record dicts sorted by delivery_start_date]}
        Returns None if the file is missing or invalid.
    """
    try:
        import geopandas as gpd
    except ImportError:
        return None

    if not os.path.exists(geojson_path):
        return None

    try:
        gdf = gpd.read_file(geojson_path)
        if gdf.empty:
            return None

        # Build grouped dict: substation_name -> sorted list of record dicts
        grouped = {}
        for _, row in gdf.iterrows():
            name = row.get("substation_name", "Unknown")
            record = {}
            for col in gdf.columns:
                if col == "geometry":
                    continue
                val = row[col]
                # Convert pandas NaT/NaN to None for clean display
                if pd.isna(val):
                    record[col] = None
                else:
                    record[col] = val
            grouped.setdefault(name, []).append(record)

        # Sort each group by delivery_start_date
        for name in grouped:
            grouped[name].sort(
                key=lambda r: str(r.get("delivery_start_date", ""))
            )

        # Dissolve geometries by substation_name (one polygon per substation)
        dissolved = gdf.dissolve(by="substation_name", aggfunc="first").reset_index()
        # Folium serializes this geometry into the component payload. A small
        # (~30 m) topology-preserving simplification substantially reduces it.
        dissolved["geometry"] = dissolved.geometry.simplify(0.0003, preserve_topology=True)

        return dissolved, grouped
    except Exception:
        return None


@st.cache_data
def load_monthly_tenders(geojson_path: str, _file_mtime: float = 0):
    """Load monthly flexibility tender polygons from GeoJSON.

    Returns
    -------
    tuple or None
        (gdf, grouped_dict) where:
        - gdf: GeoDataFrame with one row per unique substation (dissolved geometry)
        - grouped_dict: {substation_name: [list of record dicts sorted by delivery_start_date]}
        Returns None if the file is missing or invalid.
    """
    try:
        import geopandas as gpd
    except ImportError:
        return None

    if not os.path.exists(geojson_path):
        return None

    try:
        gdf = gpd.read_file(geojson_path)
        if gdf.empty:
            return None

        grouped = {}
        for _, row in gdf.iterrows():
            name = row.get("substation_name", "Unknown")
            record = {}
            for col in gdf.columns:
                if col == "geometry":
                    continue
                val = row[col]
                if pd.isna(val):
                    record[col] = None
                else:
                    record[col] = val
            grouped.setdefault(name, []).append(record)

        for name in grouped:
            grouped[name].sort(
                key=lambda r: str(r.get("delivery_start_date", ""))
            )

        dissolved = gdf.dissolve(by="substation_name", aggfunc="first").reset_index()
        dissolved["geometry"] = dissolved.geometry.simplify(0.0003, preserve_topology=True)

        return dissolved, grouped
    except Exception:
        return None


# ── Risk model helpers (cached) ──────────────────────────────────────────

@st.cache_data
def _load_published_risk_predictions(model_choice: str, _prediction_mtime: float):
    """Read only a worker-published result; never train inside Streamlit."""
    from advanced_charts.training_service import prediction_path

    path = prediction_path(model_choice)
    if not path.exists():
        return pd.DataFrame(columns=["lat", "lon", "risk_level", "confidence"])
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError):
        # Atomic publication should make this rare; keep the rest of the UI alive.
        return pd.DataFrame(columns=["lat", "lon", "risk_level", "confidence"])


def _build_recommendations(_pred_hash, _outages_len):
    """Build recommendations (no Streamlit cache — generate_report_cached handles its own caching)."""
    from advanced_charts.recommendation_engine import REPORT_CACHE, generate_report_cached

    # The report loader does not inspect its data arguments when a persistent
    # cache exists. Avoid re-reading the 100+ MB outage CSV just to load it.
    if REPORT_CACHE.exists():
        return generate_report_cached(None, None, None)

    outages_df = pd.read_csv("data/df_cleaned.csv", low_memory=False, parse_dates=["incident_date_time"])
    sites_df = pd.read_csv("data/all_charging_sites.csv", low_memory=False)
    from advanced_charts.training_service import prediction_mtime
    preds = _load_published_risk_predictions(
        "Random Forest", prediction_mtime("Random Forest")
    )
    if preds.empty:
        return {}
    return generate_report_cached(preds, outages_df, sites_df)


# ── Live incidents cache ─────────────────────────────────────────────────

@st.cache_data(ttl=300)  # Cache for 5 minutes
def _fetch_live_incidents_cached():
    """Fetch and cache live incidents for 5 minutes."""
    return fetch_live_incidents()


# ── Dataset discovery ────────────────────────────────────────────────────

def discover_datasets(dataset_dir: str):
    """Scan *dataset_dir* for compatible outage and chargepoint files.

    Returns
    -------
    tuple(list[str], list[str])
        (outage_options, site_options) — filenames only, not full paths.
    """
    ds_files = [f for f in os.listdir(dataset_dir) if os.path.isfile(os.path.join(dataset_dir, f))]

    outage_candidates = [f for f in ds_files if f.lower().endswith(('.parquet', '.csv'))]
    outage_options = [f for f in outage_candidates if f.lower().endswith('.parquet')]
    outage_options += [f for f in outage_candidates if f.lower().endswith('.csv') and 'outage' in f.lower()]
    outage_options = sorted(list(dict.fromkeys(outage_options)))
    if not outage_options:
        outage_options = ['df_cleaned.csv']

    site_options = [f for f in ds_files if f.lower().endswith('.csv') and ('site' in f.lower() or 'charging' in f.lower() or 'charge' in f.lower())]
    if 'all_charging_sites.csv' not in site_options:
        site_options.insert(0, 'all_charging_sites.csv')

    return outage_options, site_options


# ── Orchestrator ─────────────────────────────────────────────────────────

def _ensure_chart_data_cache(outages, charging_sites):
    """Precompute chart aggregation data if the disk cache is missing or stale."""
    from advanced_charts.charts import CHART_DATA_FILE, precompute_chart_data
    from advanced_charts.data import SiteData
    from advanced_charts.cache_utils import is_cache_stale_vs_source

    source = Path(__file__).parent.parent / "data" / "df_cleaned.csv"
    if CHART_DATA_FILE.exists() and not is_cache_stale_vs_source(CHART_DATA_FILE, source):
        print(f"    [  {(time.time()-time.time()):6.1f}ms] precompute_chart_data (cached)")
        return  # already cached and fresh
    if CHART_DATA_FILE.exists():
        return  # already cached

    t0 = time.time()
    sd = SiteData(outages, charging_sites)
    site_outages_map = {}
    for site_name in charging_sites['charge_point_location'].values:
        so, _ = sd.get_site_outages(site_name)
        if not so.empty:
            site_outages_map[site_name] = so
    precompute_chart_data(site_outages_map)
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] precompute_chart_data ({len(site_outages_map)} sites)")


def prepare_app_data(outage_file: str, site_file: str, filters: dict):
    """Load data, compute predictions, apply filters, fetch live incidents.

    Returns
    -------
    dict
        Keys: charging_sites, outages, filtered_outages, risk_predictions,
        risk_report, live_incidents, is_dark
    """
    from dashboard.theme import detect_dark_mode

    outage_mtime = os.path.getmtime(outage_file) if os.path.exists(outage_file) else 0
    site_mtime = os.path.getmtime(site_file) if os.path.exists(site_file) else 0
    charging_sites, outages = load_data(outage_file, site_file, outage_mtime, site_mtime)

    if charging_sites is None or outages is None:
        return None

    # Precompute chart aggregation data (once, cached to disk)
    _ensure_chart_data_cache(outages, charging_sites)

    # Risk model: consume the latest complete worker output only.
    from advanced_charts.training_service import prediction_mtime
    t0 = time.time()
    risk_predictions = _load_published_risk_predictions(
        filters["risk_model_choice"], prediction_mtime(filters["risk_model_choice"])
    )
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] load published risk predictions")
    t0 = time.time()
    risk_report = _build_recommendations(f"{len(risk_predictions)}_{filters['risk_model_choice']}", len(outages))
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] _build_recommendations")

    # Filters
    t0 = time.time()
    filtered_outages = apply_filters(outages, filters)
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] apply_filters")

    # Live incidents - use cached version
    t0 = time.time()
    live_incidents = _fetch_live_incidents_cached() if filters["show_live_incidents"] else pd.DataFrame()
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] fetch_live_incidents")

    return {
        "charging_sites": charging_sites,
        "outages": outages,
        "filtered_outages": filtered_outages,
        "risk_predictions": risk_predictions,
        "risk_report": risk_report,
        "live_incidents": live_incidents,
        "is_dark": detect_dark_mode(),
    }
