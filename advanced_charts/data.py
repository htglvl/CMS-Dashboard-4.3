"""Data access and metric computation for site-specific analysis.

Provides:
* ``SiteData`` — holds outages + charging sites, precomputes global
  metric ranges, and provides site-specific data retrieval and risk
  scoring.
* ``precompute_site_outages`` — compute and cache the site-outage
  distance matrix so subsequent loads are instant.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / "data"
CACHE_FILE = CACHE_DIR / "site_outage_cache.pkl"
BUFFER_KM = 3.218  # 2 miles


def outages_within_radius(outages_df, lat, lon, radius_km=BUFFER_KM):
    """Return rows of *outages_df* within *radius_km* of (lat, lon).

    Uses Haversine distance.  Returns a copy so callers can mutate safely.
    """
    if outages_df.empty:
        return outages_df.copy()

    out_lat = np.radians(outages_df['latitude'].values)
    out_lon = np.radians(outages_df['longitude'].values)
    lat0 = np.radians(lat)
    lon0 = np.radians(lon)
    dlat = out_lat - lat0
    dlon = out_lon - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat0) * np.cos(out_lat) * np.sin(dlon / 2) ** 2
    distances_km = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))
    return outages_df[distances_km <= radius_km].copy()


def _scale(value, min_val, max_val):
    """Min-max scale value to 0-100. Returns 50 when range is zero."""
    return ((value - min_val) / (max_val - min_val) * 100) if max_val > min_val else 50.0


# ---------------------------------------------------------------------------
# Precomputation
# ---------------------------------------------------------------------------

def precompute_site_outages(outages: pd.DataFrame, charging_sites: pd.DataFrame, force: bool = False) -> dict:
    """Precompute per-site outage indices and global metric ranges.

    Saves the result to ``data/site_outage_cache.pkl`` and returns the
    cache dict.  If the cache already exists and *force* is False, the
    existing cache is returned without recomputing.

    Parameters
    ----------
    outages : pd.DataFrame
        Full outage dataset.
    charging_sites : pd.DataFrame
        Charging site locations.
    force : bool
        If True, recompute even if cache exists.

    Returns
    -------
    dict
        Keys: ``site_indices`` (dict[str, np.ndarray]), ``metric_min_max`` (dict),
        ``outage_count`` (int), ``site_count`` (int).
    """
    import joblib

    if CACHE_FILE.exists() and not force:
        log.info("Loading site-outage cache from %s", CACHE_FILE)
        return joblib.load(CACHE_FILE)

    log.info("Precomputing site-outage cache (%d sites, %d outages)...",
             len(charging_sites), len(outages))

    if outages.empty or charging_sites.empty:
        cache = {"site_indices": {}, "metric_min_max": _empty_metric_ranges(), "outage_count": 0, "site_count": 0}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(cache, CACHE_FILE)
        return cache

    # Vectorised Haversine: (n_sites, n_outages)
    out_lat = np.radians(outages['latitude'].values)
    out_lon = np.radians(outages['longitude'].values)
    site_lat = np.radians(charging_sites['latitude'].values)
    site_lon = np.radians(charging_sites['longitude'].values)

    dlat = site_lat[:, None] - out_lat[None, :]
    dlon = site_lon[:, None] - out_lon[None, :]
    a = (np.sin(dlat / 2) ** 2
         + np.cos(site_lat[:, None]) * np.cos(out_lat[None, :]) * np.sin(dlon / 2) ** 2)
    dist_km = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))
    mask = dist_km <= BUFFER_KM  # (n_sites, n_outages) boolean

    # Per-site outage indices
    site_indices = {}
    site_names = charging_sites['charge_point_location'].values
    for i, name in enumerate(site_names):
        idx = np.where(mask[i])[0]
        site_indices[name] = idx

    # Global metric ranges (for normalisation)
    dur = outages['duration-hours'].values
    impact = outages['Total Customer Minutes Lost'].values

    n_sites = len(charging_sites)
    freq_arr = mask.sum(axis=1).astype(float)
    dur_arr = np.zeros(n_sites)
    imp_arr = np.zeros(n_sites)
    cv_arr = np.zeros(n_sites)

    for i in range(n_sites):
        site_mask = mask[i]
        if not site_mask.any():
            continue
        site_dur = dur[site_mask]
        dur_arr[i] = site_dur.mean()
        imp_arr[i] = impact[site_mask].sum() / 60.0
        std = site_dur.std()
        if dur_arr[i] and not np.isnan(std):
            cv_arr[i] = std / dur_arr[i]

    def _mm(vals):
        mn, mx = vals.min(), vals.max()
        return (mn, mn + 1.0) if mx == mn else (mn, mx)

    metric_min_max = {
        'freq_min': _mm(freq_arr)[0], 'freq_max': _mm(freq_arr)[1],
        'duration_min': _mm(dur_arr)[0], 'duration_max': _mm(dur_arr)[1],
        'impact_min': _mm(imp_arr)[0], 'impact_max': _mm(imp_arr)[1],
        'cv_min': _mm(cv_arr)[0], 'cv_max': _mm(cv_arr)[1],
    }

    cache = {
        "site_indices": site_indices,
        "metric_min_max": metric_min_max,
        "outage_count": len(outages),
        "site_count": n_sites,
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(cache, CACHE_FILE)
    log.info("Cache saved to %s", CACHE_FILE)
    return cache


def _empty_metric_ranges() -> dict:
    return {k: (0, 1) for k in ('freq', 'duration', 'impact', 'cv')}


# In-memory cache to avoid re-reading pickle from disk on every call
_mem_cache: dict | None = None
_mem_cache_mtime: float = 0.0


def load_cache() -> dict | None:
    """Load the precomputed cache if it exists, else None.

    Uses an in-memory cache to avoid re-reading the pickle file on
    every call.  The file is only re-read if it has been modified.
    """
    global _mem_cache, _mem_cache_mtime
    import joblib

    if not CACHE_FILE.exists():
        _mem_cache = None
        return None

    mtime = CACHE_FILE.stat().st_mtime
    if _mem_cache is not None and mtime == _mem_cache_mtime:
        return _mem_cache

    _mem_cache = joblib.load(CACHE_FILE)
    _mem_cache_mtime = mtime
    return _mem_cache


def invalidate_cache():
    """Delete the cache file (called after a new data fetch)."""
    global _mem_cache, _mem_cache_mtime
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        log.info("Site-outage cache invalidated: %s", CACHE_FILE)
    _mem_cache = None
    _mem_cache_mtime = 0.0


# ---------------------------------------------------------------------------
# SiteData
# ---------------------------------------------------------------------------

class SiteData:
    """Data access layer for site-specific outage analysis.

    Uses precomputed cache if available.  Falls back to on-the-fly
    Haversine computation if no cache exists.
    """

    def __init__(self, outages: pd.DataFrame, charging_sites: pd.DataFrame):
        # Skip .copy() — callers don't mutate, and @st.cache_resource
        # keeps the same object alive across reruns.
        self.outages = outages if outages is not None else pd.DataFrame()
        self.charging_sites = charging_sites if charging_sites is not None else pd.DataFrame()

        # Load precomputed cache.
        # metric_min_max are GLOBAL normalization constants — they never
        # change when filtering, so always use the cached version.
        # _site_indices only match when the unfiltered dataset is loaded.
        cache = load_cache()
        self.metric_min_max = (cache["metric_min_max"] if cache
                               else self._compute_global_metric_ranges())

        if (cache
            and cache.get("outage_count") == len(self.outages)
            and cache.get("site_count") == len(self.charging_sites)):
            self._site_indices = cache["site_indices"]
        else:
            # Filtered data: indices won't align, so fall back to on-the-fly.
            self._site_indices = None

    def get_site_outages(self, site_name: str, buffer_radius_km: float = BUFFER_KM):
        """Return outages within *buffer_radius_km* of *site_name* and the site row."""
        site_info = self.charging_sites[
            self.charging_sites['charge_point_location'] == site_name
        ].iloc[0]

        if self.outages.empty:
            return pd.DataFrame(), site_info

        # Use cache if available
        if self._site_indices is not None and site_name in self._site_indices:
            idx = self._site_indices[site_name]
            return self.outages.iloc[idx].copy(), site_info

        # Fallback: on-the-fly Haversine
        return outages_within_radius(self.outages, site_info['latitude'],
                                     site_info['longitude'], buffer_radius_km), site_info

    def _compute_global_metric_ranges(self) -> dict:
        """Precompute min/max for frequency, duration, impact, CV across all sites."""
        n_sites = len(self.charging_sites)
        if self.outages.empty or n_sites == 0:
            return {k: (0, 1) for k in ('freq', 'duration', 'impact', 'cv')}

        out_lat = np.radians(self.outages['latitude'].values)
        out_lon = np.radians(self.outages['longitude'].values)
        site_lat = np.radians(self.charging_sites['latitude'].values)
        site_lon = np.radians(self.charging_sites['longitude'].values)

        dlat = site_lat[:, None] - out_lat[None, :]
        dlon = site_lon[:, None] - out_lon[None, :]
        a = (np.sin(dlat / 2) ** 2
             + np.cos(site_lat[:, None]) * np.cos(out_lat[None, :]) * np.sin(dlon / 2) ** 2)
        dist_km = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))
        mask = dist_km <= 3.218

        dur = self.outages['duration-hours'].values
        impact = self.outages['Total Customer Minutes Lost'].values

        freq_arr = mask.sum(axis=1).astype(float)
        dur_arr = np.zeros(n_sites)
        imp_arr = np.zeros(n_sites)
        cv_arr = np.zeros(n_sites)

        for i in range(n_sites):
            site_mask = mask[i]
            if not site_mask.any():
                continue
            site_dur = dur[site_mask]
            dur_arr[i] = site_dur.mean()
            imp_arr[i] = impact[site_mask].sum() / 60.0
            std = site_dur.std()
            if dur_arr[i] and not np.isnan(std):
                cv_arr[i] = std / dur_arr[i]

        def _mm(vals):
            mn, mx = vals.min(), vals.max()
            return (mn, mn + 1.0) if mx == mn else (mn, mx)

        return {
            'freq_min': _mm(freq_arr)[0], 'freq_max': _mm(freq_arr)[1],
            'duration_min': _mm(dur_arr)[0], 'duration_max': _mm(dur_arr)[1],
            'impact_min': _mm(imp_arr)[0], 'impact_max': _mm(imp_arr)[1],
            'cv_min': _mm(cv_arr)[0], 'cv_max': _mm(cv_arr)[1],
        }

    def compute_risk_metrics(self, site_outages: pd.DataFrame) -> dict:
        """Compute normalised risk scores for a site's outages.

        Returns dict with keys: Frequency Score, Duration Score,
        Impact Score, Consistency Score, Overall Score.
        """
        if site_outages.empty:
            return {}

        freq = len(site_outages)
        avg_duration = site_outages['duration-hours'].mean()
        impact = site_outages['Total Customer Minutes Lost'].sum() / 60
        std_dur = site_outages['duration-hours'].std()
        cv = (std_dur / avg_duration) if avg_duration and not np.isnan(std_dur) else 0

        mm = self.metric_min_max
        freq_score = _scale(freq, mm['freq_min'], mm['freq_max'])
        dur_score = _scale(avg_duration, mm['duration_min'], mm['duration_max'])
        imp_score = _scale(impact, mm['impact_min'], mm['impact_max'])
        consistency_score = _scale(mm['cv_max'] - cv, mm['cv_min'], mm['cv_max'])
        overall = (freq_score + dur_score + imp_score + consistency_score) / 4.0

        return {
            'Frequency Score': freq_score,
            'Duration Score': dur_score,
            'Impact Score': imp_score,
            'Consistency Score': consistency_score,
            'Overall Score': overall,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

    parser = argparse.ArgumentParser(description="Precompute site-outage cache.")
    parser.add_argument("--force", action="store_true", help="Force recomputation even if cache exists")
    args = parser.parse_args()

    outages_path = CACHE_DIR / "df_cleaned.csv"
    sites_path = CACHE_DIR / "all_charging_sites.csv"

    if not outages_path.exists():
        print(f"Error: {outages_path} not found")
    elif not sites_path.exists():
        print(f"Error: {sites_path} not found")
    else:
        outages = pd.read_csv(outages_path, low_memory=False, parse_dates=["incident_date_time"])
        sites = pd.read_csv(sites_path, low_memory=False)
        cache = precompute_site_outages(outages, sites, force=args.force)
        print(f"Cache ready: {cache['site_count']} sites, {cache['outage_count']} outages")
