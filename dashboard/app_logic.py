"""Application logic — data loading, risk model computation, filtering.

All functions here are pure data operations with no Streamlit UI calls.
"""

import os
import time
import pandas as pd
import streamlit as st

from data.fetch_live_incidents import fetch_live_incidents
from advanced_charts.risk_model import (
    build_grid_features_cached, assign_risk_labels,
    load_models as load_risk_models, predict_cells,
)
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


# ── Risk model helpers (cached) ──────────────────────────────────────────

@st.cache_resource
def _load_risk_models_cached():
    return load_risk_models()


@st.cache_data(ttl=1800)  # Cache for 30 minutes
def _compute_risk_predictions(_outages_hash, model_choice, _outages_len):
    """Compute risk predictions (cached by data hash and model choice)."""
    outages_df = pd.read_csv("data/df_cleaned.csv", low_memory=False, parse_dates=["incident_date_time"])
    features = build_grid_features_cached(outages_df)
    features = assign_risk_labels(features)
    rf_model, xgb_model, xgb_le = _load_risk_models_cached()
    if model_choice == "XGBoost":
        return predict_cells(xgb_model, features, xgb_le)
    return predict_cells(rf_model, features)


@st.cache_data(ttl=1800)  # Cache for 30 minutes
def _build_recommendations(_pred_hash, _outages_len):
    from advanced_charts.recommendation_engine import generate_report_cached
    outages_df = pd.read_csv("data/df_cleaned.csv", low_memory=False, parse_dates=["incident_date_time"])
    sites_df = pd.read_csv("data/all_charging_sites.csv", low_memory=False)
    preds = _compute_risk_predictions(_pred_hash, "Random Forest", _outages_len)
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
    """Precompute chart aggregation data if the disk cache is missing."""
    from advanced_charts.charts import CHART_DATA_FILE, precompute_chart_data
    from advanced_charts.data import SiteData

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

    # Risk model - use cached version
    outages_hash = f"{len(outages)}_{outages['incident_date_time'].max()}"
    t0 = time.time()
    risk_predictions = _compute_risk_predictions(outages_hash, filters["risk_model_choice"], len(outages))
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] _compute_risk_predictions")
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
