"""Plotly chart factory functions for site-specific analysis.

All functions are standalone — they accept data as parameters and return
a ``plotly.graph_objects.Figure``.  No class state is required.
"""

import time
import logging
from pathlib import Path

import streamlit as st
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from advanced_charts.data import SiteData

log = logging.getLogger(__name__)

MONTH_ORDER = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]

# ── Per-site chart figure cache (in-memory, survives reruns) ────────────
_chart_cache: dict[str, dict] = {}


def _get_cached(site_name: str, chart_key: str):
    """Return a cached chart figure, or None."""
    return _chart_cache.get(site_name, {}).get(chart_key)


def _set_cached(site_name: str, chart_key: str, fig):
    """Cache a chart figure."""
    _chart_cache.setdefault(site_name, {})[chart_key] = fig


def invalidate_chart_cache():
    """Clear the in-memory chart figure cache (called after new data fetch)."""
    _chart_cache.clear()
    log.info("Chart figure cache cleared")


# ── Precomputed chart data cache (disk + memory) ────────────────────────
CHART_CACHE_DIR = Path(__file__).parent.parent / "data"
CHART_DATA_FILE = CHART_CACHE_DIR / "chart_data_cache.pkl"

_chart_data_mem: dict | None = None
_chart_data_mtime: float = 0.0


def _load_chart_data_cache() -> dict:
    """Load precomputed chart data from disk (with in-memory cache)."""
    global _chart_data_mem, _chart_data_mtime
    import joblib

    if not CHART_DATA_FILE.exists():
        _chart_data_mem = {}
        return {}

    mtime = CHART_DATA_FILE.stat().st_mtime
    if _chart_data_mem is not None and mtime == _chart_data_mtime:
        return _chart_data_mem

    _chart_data_mem = joblib.load(CHART_DATA_FILE)
    _chart_data_mtime = mtime
    return _chart_data_mem


def precompute_chart_data(site_outages_map: dict[str, pd.DataFrame]):
    """Precompute aggregated DataFrames for freq_timeline and customer_hours per site.

    Parameters
    ----------
    site_outages_map : dict[str, pd.DataFrame]
        Mapping of site_name → site_outages DataFrame (unfiltered).
    """
    import joblib

    log.info("Precomputing chart data for %d sites...", len(site_outages_map))
    cache = {}

    for site_name, site_outages in site_outages_map.items():
        if site_outages.empty:
            continue
        cache[site_name] = {
            "freq_timeline": _aggregate_freq_timeline(site_outages),
            "customer_hours": _aggregate_customer_hours(site_outages),
        }

    CHART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(cache, CHART_DATA_FILE)
    global _chart_data_mem, _chart_data_mtime
    _chart_data_mem = cache
    _chart_data_mtime = CHART_DATA_FILE.stat().st_mtime
    log.info("Chart data cache saved: %d sites", len(cache))


def invalidate_chart_data_cache():
    """Delete the chart data pickle (called after new data fetch)."""
    global _chart_data_mem, _chart_data_mtime
    if CHART_DATA_FILE.exists():
        CHART_DATA_FILE.unlink()
        log.info("Chart data cache invalidated: %s", CHART_DATA_FILE)
    _chart_data_mem = None
    _chart_data_mtime = 0.0
    # Also clear figure cache since data has changed
    invalidate_chart_cache()


# ── Aggregation helpers (pure DataFrame work, no Plotly) ────────────────

def _aggregate_freq_timeline(site_outages: pd.DataFrame) -> pd.DataFrame | None:
    """Return the merged DataFrame for freq_timeline, or None."""
    if 'month_name' not in site_outages.columns or 'year' not in site_outages.columns:
        return None

    temp = site_outages[['month_name', 'year', 'duration_category']].copy()
    temp['month_number'] = temp['month_name'].apply(
        lambda m: MONTH_ORDER.index(m) + 1 if m in MONTH_ORDER else None
    )
    temp['year_month'] = temp['year'].astype(str) + '-' + temp['month_number'].astype(str).str.zfill(2)
    temp['year_month_label'] = temp['month_name'] + ' ' + temp['year'].astype(str)
    grouped = temp.groupby(['year_month', 'year_month_label', 'duration_category']).size().reset_index(name='count')
    unique_months = sorted(grouped['year_month'].unique())
    full_range = pd.DataFrame({'year_month': unique_months})
    label_map = grouped.set_index('year_month')['year_month_label'].to_dict()
    full_range['year_month_label'] = full_range['year_month'].map(label_map)
    categories = grouped['duration_category'].unique()
    full_grid = full_range.assign(key=1).merge(
        pd.DataFrame({'duration_category': categories, 'key': 1}), on='key'
    ).drop('key', axis=1)
    merged = full_grid.merge(grouped, on=['year_month', 'year_month_label', 'duration_category'], how='left')
    merged['count'] = merged['count'].fillna(0)
    return merged.sort_values('year_month')


def _aggregate_customer_hours(site_outages: pd.DataFrame) -> pd.DataFrame | None:
    """Return the merged DataFrame for customer_hours timeline, or None."""
    if 'month_name' not in site_outages.columns or 'year' not in site_outages.columns:
        return None

    temp = site_outages[['month_name', 'year', 'Total Customer Minutes Lost']].copy()
    temp['customer_hours_lost'] = temp['Total Customer Minutes Lost'] / 60
    temp2 = temp.copy()
    temp2['month_number'] = temp2['month_name'].apply(
        lambda m: MONTH_ORDER.index(m) + 1 if m in MONTH_ORDER else None
    )
    temp2['year_month'] = temp2['year'].astype(str) + '-' + temp2['month_number'].astype(str).str.zfill(2)
    temp2['year_month_label'] = temp2['month_name'] + ' ' + temp2['year'].astype(str)
    grouped = temp2.groupby(['year_month', 'year_month_label'])['customer_hours_lost'].mean().reset_index()
    unique_months = sorted(grouped['year_month'].unique())
    full_range = pd.DataFrame({'year_month': unique_months})
    label_map = grouped.set_index('year_month')['year_month_label'].to_dict()
    full_range['year_month_label'] = full_range['year_month'].map(label_map)
    merged = full_range.merge(grouped, on=['year_month', 'year_month_label'], how='left')
    merged['customer_hours_lost'] = merged['customer_hours_lost'].fillna(0)
    return merged.sort_values('year_month')


def _empty_chart(message: str):
    """Return a blank chart displaying *message*."""
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color="gray"),
    )
    fig.update_layout(
        height=400,
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
    )
    return fig


def create_frequency_timeline(site_outages: pd.DataFrame, site_name: str):
    """Line chart of outage count per month by duration category."""
    cached = _get_cached(site_name, "freq_timeline")
    if cached is not None:
        return cached
    if site_outages.empty:
        return _empty_chart("No outage data available")

    t0 = time.time()

    # Try precomputed aggregation from disk cache
    chart_data = _load_chart_data_cache()
    precomputed = chart_data.get(site_name, {}).get("freq_timeline")
    if precomputed is not None:
        merged = precomputed
        x_col, y_col, color_col = 'year_month_label', 'count', 'duration_category'
    elif 'month_name' in site_outages.columns and 'year' in site_outages.columns:
        # Fallback: compute on the fly
        merged = _aggregate_freq_timeline(site_outages)
        if merged is None:
            return _empty_chart("No outage data available")
        x_col, y_col, color_col = 'year_month_label', 'count', 'duration_category'
    else:
        temp = site_outages.copy()
        grouped = temp.groupby(['year', 'duration_category']).size().reset_index(name='count')
        unique_years = sorted(grouped['year'].unique())
        categories = grouped['duration_category'].unique()
        full_range = pd.DataFrame({'year': unique_years})
        full_grid = full_range.assign(key=1).merge(
            pd.DataFrame({'duration_category': categories, 'key': 1}), on='key'
        ).drop('key', axis=1)
        merged = full_grid.merge(grouped, on=['year', 'duration_category'], how='left')
        merged['count'] = merged['count'].fillna(0)
        x_col, y_col, color_col = 'year', 'count', 'duration_category'

    fig = px.line(
        merged, x=x_col, y=y_col, color=color_col,
        title=f'Outage Frequency Over Time - {site_name}',
        labels={y_col: 'Number of Outages', x_col: 'Time', color_col: 'Duration Category'},
        markers=True,
    )
    max_count = merged[y_col].max() if not merged.empty else 1
    fig.update_yaxes(range=[0, max_count * 1.1])
    fig.update_xaxes(tickangle=90)
    fig.update_layout(
        height=400, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] freq_timeline (compute)")
    _set_cached(site_name, "freq_timeline", fig)
    return fig


def create_customer_hours_timeline(site_outages: pd.DataFrame, site_name: str):
    """Line chart of average customer-hours lost per month."""
    cached = _get_cached(site_name, "customer_hours")
    if cached is not None:
        return cached
    if site_outages.empty:
        return _empty_chart("No customer data available")

    t0 = time.time()

    # Try precomputed aggregation from disk cache
    chart_data = _load_chart_data_cache()
    precomputed = chart_data.get(site_name, {}).get("customer_hours")
    if precomputed is not None:
        merged = precomputed
        x_col, y_col = 'year_month_label', 'customer_hours_lost'
    elif 'month_name' in site_outages.columns and 'year' in site_outages.columns:
        # Fallback: compute on the fly
        merged = _aggregate_customer_hours(site_outages)
        if merged is None:
            return _empty_chart("No customer data available")
        x_col, y_col = 'year_month_label', 'customer_hours_lost'
    else:
        temp = site_outages.copy()
        temp['customer_hours_lost'] = temp['Total Customer Minutes Lost'] / 60
        grouped = temp.groupby('year')['customer_hours_lost'].mean().reset_index()
        unique_years = sorted(grouped['year'].unique())
        full_range = pd.DataFrame({'year': unique_years})
        merged = full_range.merge(grouped, on='year', how='left')
        merged['customer_hours_lost'] = merged['customer_hours_lost'].fillna(0)
        x_col, y_col = 'year', 'customer_hours_lost'

    fig = px.line(
        merged, x=x_col, y=y_col,
        title=f'Average Customer Hours Lost Over Time - {site_name}',
        labels={y_col: 'Avg Customer Hours Lost', x_col: 'Time'},
        markers=True,
    )
    max_val = merged[y_col].max() if not merged.empty else 1
    fig.update_yaxes(range=[0, max_val * 1.1])
    fig.update_traces(line_color='#FF6B6B')
    fig.update_layout(height=400)
    fig.update_xaxes(tickangle=90)
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] customer_hours (compute)")
    _set_cached(site_name, "customer_hours", fig)
    return fig


def create_duration_impact_pie(site_outages: pd.DataFrame, site_name: str):
    """Pie chart of customer-hours lost by duration category."""
    cached = _get_cached(site_name, "impact_pie")
    if cached is not None:
        return cached
    if site_outages.empty:
        return _empty_chart("No duration data available")

    t0 = time.time()
    customer_hours = site_outages['Total Customer Minutes Lost'].values / 60
    duration_impact = (
        site_outages.assign(customer_hours_lost=customer_hours)
        .groupby('duration_category')['customer_hours_lost'].sum().reset_index()
    )
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] impact_pie (groupby)")

    t0 = time.time()
    fig = px.pie(
        duration_impact, values='customer_hours_lost', names='duration_category',
        title=f'Customer Impact by Outage Duration - {site_name}',
        color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig.update_layout(height=400)
    print(f"    [  {(time.time()-t0)*1000:6.1f}ms] impact_pie (plotly)")
    _set_cached(site_name, "impact_pie", fig)
    return fig


def create_duration_frequency_pie(site_outages: pd.DataFrame, site_name: str):
    """Pie chart of outage count by duration category."""
    cached = _get_cached(site_name, "freq_pie")
    if cached is not None:
        return cached
    if site_outages.empty:
        return _empty_chart("No frequency data available")

    duration_freq = site_outages['duration_category'].value_counts().reset_index()
    duration_freq.columns = ['duration_category', 'count']

    fig = px.pie(
        duration_freq, values='count', names='duration_category',
        title=f'Outage Frequency by Duration - {site_name}',
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_layout(height=400)
    _set_cached(site_name, "freq_pie", fig)
    return fig


def create_risk_assessment_chart(site_outages: pd.DataFrame, site_name: str, scores: dict):
    """Radar chart of normalised risk metrics for *site_name*."""
    cached = _get_cached(site_name, "risk_radar")
    if cached is not None:
        return cached
    if site_outages.empty or not scores:
        return _empty_chart("No risk data available")

    categories = list(scores.keys())
    values = list(scores.values())

    # Close polygon
    categories.append(categories[0])
    values.append(values[0])

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        name=site_name,
    ))
    fig.update_layout(
        template = 'plotly_dark' if st.get_option("theme.base") == "dark" else 'plotly_white',
        polar=dict(
            bgcolor='rgba(0,0,0,0)' if st.get_option("theme.base") == "dark" else 'rgba(255,255,255,0)', 
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(
                    color='rgb(255,0,0)'
                )
            ),
        ),
        title=f'Risk Assessment Profile - {site_name}',
        showlegend=True,
        height=400
    )
    _set_cached(site_name, "risk_radar", fig)
    return fig
