"""Sidebar filters, controls, and auto-refresh configuration."""

import os
import time as _time
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh


class OutlierFilter:
    """Statistical filtering using IQR and significance measures."""

    @staticmethod
    def filter_duration_outliers(df, column='duration-hours', method='IQR', iqr_multiplier=1.5):
        if method == 'IQR' and not df.empty:
            Q1 = df[column].quantile(0.25)
            Q3 = df[column].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = max(0, Q1 - iqr_multiplier * IQR)
            upper_bound = min(49, Q3 + iqr_multiplier * IQR)
            filtered_df = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)].copy()
            removed_count = len(df) - len(filtered_df)
            if len(df) > 0:
                st.sidebar.info(f"IQR Filter: Removed {removed_count:,} outliers ({removed_count/len(df)*100:.1f}%)")
            return filtered_df
        return df.copy()

    @staticmethod
    def calculate_significance_ratio(df, threshold_quantile=0.5):
        if df.empty:
            return df.copy()
        df = df.copy()
        if 'duration-hours' in df.columns:
            df['significance_ratio'] = df['Total Customer Minutes Lost'] / (df['duration-hours'] * 60)
        else:
            df['significance_ratio'] = 0
        df['significance_ratio'] = df['significance_ratio'].fillna(0)
        threshold_quantile = max(0.0, min(1.0, threshold_quantile))
        significance_threshold = df['significance_ratio'].quantile(threshold_quantile)
        filtered_df = df[df['significance_ratio'] >= significance_threshold].copy()
        removed_count = len(df) - len(filtered_df)
        if len(df) > 0:
            st.sidebar.info(f"Significance Filter: Removed {removed_count:,} low-impact outages ({removed_count/len(df)*100:.1f}%)")
        return filtered_df


def render_sidebar(charging_sites, outages):
    """Render all sidebar controls and return filter/setting values.

    Returns
    -------
    dict
        Keys: years, daytime_only, exclude_exceptional, selected_categories,
        use_iqr_filter, use_significance_filter, iqr_multiplier,
        significance_quantile, show_buffers, show_heatmap,
        refresh_interval_min, show_live_incidents, live_refresh_min,
        live_refresh_label, risk_model_choice, show_risk_heatmap
    """
    st.sidebar.header("Advanced Filters")

    # Year filter
    available_years = sorted(outages['year'].unique()) if 'year' in outages.columns else [2023, 2024, 2025]
    years = st.sidebar.multiselect("Years", options=available_years, default=available_years)

    # Time filter
    daytime_only = st.sidebar.checkbox("Daytime only (9AM-9PM)", value=True)

    # Exclude exceptional events
    exclude_exceptional = st.sidebar.checkbox("Exclude exceptional events", value=True)

    # Category filter
    selected_categories = st.sidebar.multiselect(
        "Chargepoint Categories",
        options=charging_sites['site_category'].unique(),
        default=charging_sites['site_category'].unique()
    )

    # Statistical filtering
    st.sidebar.subheader("Statistical Filters")
    use_iqr_filter = st.sidebar.checkbox("Apply IQR outlier removal", value=True)
    use_significance_filter = st.sidebar.checkbox("Apply significance filter", value=True)

    st.sidebar.subheader("Filter Parameters")
    iqr_multiplier = st.sidebar.slider(
        "IQR multiplier", min_value=0.0, max_value=4.0, value=1.5, step=0.1,
        help="Adjust how aggressively outliers are removed. Higher values keep more data."
    )
    significance_quantile = st.sidebar.slider(
        "Significance threshold (quantile)", min_value=0.0, max_value=1.0, value=0.5, step=0.05,
        help="Select the minimum quantile for high-impact outages. 0.5 corresponds to the median."
    )

    # Auto-refresh
    st.sidebar.subheader("Auto-Refresh")
    refresh_options = {
        "30 seconds": 0.5, "Hourly": 60, "Daily": 1440,
        "Weekly": 10080, "Monthly": 43200,
    }
    refresh_label = st.sidebar.selectbox(
        "Data refresh interval", options=list(refresh_options.keys()), index=1,
        help="How often to fetch new outage data from the ENW API and refresh the page."
    )
    refresh_interval_min = refresh_options[refresh_label]

    # Live incidents refresh
    live_refresh_options = {
        "15 minutes": 15, "30 minutes": 30, "1 hour": 60,
        "2 hours": 120, "Disabled": None,
    }
    live_refresh_label = st.sidebar.selectbox(
        "Live incidents refresh", options=list(live_refresh_options.keys()), index=1,
        help="How often to check for new live incidents. Select 'Disabled' to hide."
    )
    live_refresh_min = live_refresh_options[live_refresh_label]
    show_live_incidents = live_refresh_min is not None

    # Risk prediction
    st.sidebar.subheader("Risk Prediction")
    risk_model_choice = st.sidebar.selectbox(
        "Prediction model", options=["Random Forest", "XGBoost"], index=0,
        help="Random Forest is more explainable; XGBoost may be more accurate."
    )

    return {
        "years": years,
        "daytime_only": daytime_only,
        "exclude_exceptional": exclude_exceptional,
        "selected_categories": selected_categories,
        "use_iqr_filter": use_iqr_filter,
        "use_significance_filter": use_significance_filter,
        "iqr_multiplier": iqr_multiplier,
        "significance_quantile": significance_quantile,
        "show_chargepoints": True,  # Always show
        "show_buffers": True,  # Always show, toggleable via layer control
        "show_heatmap": True,  # Always show
        "refresh_interval_min": refresh_interval_min,
        "show_live_incidents": show_live_incidents,
        "live_refresh_min": live_refresh_min,
        "live_refresh_label": live_refresh_label,
        "risk_model_choice": risk_model_choice,
        "show_risk_heatmap": True,  # Always show risk heatmap
    }


def setup_autorefresh(refresh_interval_min, show_live_incidents, live_refresh_min):
    """Configure auto-refresh timers."""
    st_autorefresh(
        interval=refresh_interval_min * 60 * 1000,
        key="periodic_data_refresh",
    )
    if show_live_incidents:
        st_autorefresh(
            interval=live_refresh_min * 60 * 1000,
            key="live_incidents_refresh",
        )


def maybe_fetch_outage_data(refresh_interval_min):
    """Periodically fetch new outage data from the ENW API."""
    if "_last_outage_fetch_ts" not in st.session_state:
        st.session_state["_last_outage_fetch_ts"] = 0.0

    _elapsed = _time.time() - st.session_state["_last_outage_fetch_ts"]
    if _elapsed >= refresh_interval_min * 60:
        try:
            from data.fetch_outages import run_daily_fetch
            # Show status in sidebar without blocking the page
            fetch_status = st.sidebar.empty()
            fetch_status.caption("🔄 Checking for updates...")
            result = run_daily_fetch()
            if result.get("error"):
                fetch_status.warning(f"⚠️ {result['error']}")
            elif not result.get("skipped"):
                if result.get("fetched", 0) > 0:
                    fetch_status.success(f"⚡ Fetched {result['fetched']:,} new records")
                    st.toast(f"Fetched {result['fetched']:,} new outage records.", icon="⚡")
                    from enhanced_app import load_data
                    load_data.clear()
                else:
                    fetch_status.success("✔ Up to date")
                    st.toast("Outage data is already up to date.", icon="✔")
            else:
                fetch_status.empty()
            st.session_state["_last_outage_fetch_ts"] = _time.time()
        except (ImportError, Exception):
            pass


def apply_filters(outages, filters):
    """Apply sidebar filter selections to the outage DataFrame.

    Returns
    -------
    pd.DataFrame
        Filtered outages.
    """
    filtered = outages.copy()

    if filters["years"] and 'year' in filtered.columns:
        filtered = filtered[filtered['year'].isin(filters["years"])]

    if filters["daytime_only"] and 'hour' in filtered.columns:
        filtered = filtered[(filtered['hour'] >= 9) & (filtered['hour'] <= 21)]

    if filters["exclude_exceptional"] and 'is_exceptional_event' in filtered.columns:
        filtered = filtered[~filtered['is_exceptional_event'].fillna(False).astype(bool)]

    if filters["use_iqr_filter"] and 'duration-hours' in filtered.columns:
        filtered = OutlierFilter.filter_duration_outliers(filtered, iqr_multiplier=filters["iqr_multiplier"])

    if filters["use_significance_filter"]:
        filtered = OutlierFilter.calculate_significance_ratio(filtered, threshold_quantile=filters["significance_quantile"])

    return filtered
