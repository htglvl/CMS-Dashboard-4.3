"""
CMS Grid Resilience AI Dashboard — main entry point.

This file handles page configuration, CSS, and UI rendering only.
All data logic lives in ``dashboard/app_logic.py``.
"""

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from dashboard.app_logic import discover_datasets, prepare_app_data, load_data, load_flexibility_tenders
from dashboard.sidebar import render_sidebar, setup_autorefresh, maybe_fetch_outage_data
from dashboard.map import create_advanced_map
from dashboard.chart_display import display_dynamic_charts
from dashboard.click_processor import process_map_click
from dashboard.metrics import render_ai_dashboard
from dashboard.live_incidents import render_live_incidents

# ── Page config (must be first Streamlit command) ────────────────────────
st.set_page_config(
    page_title="CMS Grid Resilience Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    color: #FF1493;
    text-align: center;
    margin-bottom: 1rem;
}
.metric-card {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 5px solid #FF1493;
    margin: 0.5rem 0;
}
.insight-box {
    background-color: #e8f4fd;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 5px solid #007acc;
    margin: 0.5rem 0;
    color: #000;
}
.warning-box {
    background-color: #fff3cd;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 5px solid #ffc107;
    margin: 0.5rem 0;
}

/* Make spinner full width */
.stSpinner > div {
    position: relative !important;
    width: 100% !important;
}

/* Remove grey overlay from spinner */
.stSpinner::before {
    display: none !important;
}

/* Style the spinner message to be full width and readable */
.stSpinner > div > div {
    width: 100% !important;
    max-width: 100% !important;
}

/* Make st.status containers full width */
[data-testid="stStatusWidget"] {
    width: 100% !important;
}

/* Hide heading anchor link buttons */
h1 > a, h2 > a, h3 > a {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)


def _ts(msg, t0):
    """Print a timing line to console and return current time."""
    t1 = time.time()
    print(f"  [{(t1-t0)*1000:7.1f}ms] {msg}")
    return t1


def main():
    t_main = time.time()
    print("\n=== Dashboard main() ===")

    # Initialize session state for pin
    if "pin_lat" not in st.session_state:
        st.session_state.pin_lat = None
    if "pin_lng" not in st.session_state:
        st.session_state.pin_lng = None
    if "selected_site" not in st.session_state:
        st.session_state.selected_site = None
    if "last_popup_html" not in st.session_state:
        st.session_state.last_popup_html = None
    if "flex_selected_substation" not in st.session_state:
        st.session_state.flex_selected_substation = None
    if "flex_page_index" not in st.session_state:
        st.session_state.flex_page_index = 0

    st.markdown('<h1 class="main-header">CMS Grid Resilience AI Dashboard</h1>', unsafe_allow_html=True)

    # ── OpenClaw AI Chat button ──────────────────────────────────────────
    _oclaw_href = "/oclaw/"

    st.sidebar.markdown(f"""
    <style>
    .openclaw-btn {{
        display: block;
        width: 100%;
        padding: 12px 16px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
        text-align: center;
        font-size: 1.1em;
        font-weight: 700;
        border-radius: 8px;
        text-decoration: none;
        margin-bottom: 16px;
        transition: opacity 0.2s;
    }}
    .openclaw-btn:hover {{
        opacity: 0.85;
        text-decoration: none;
    }}
    </style>
    <a class="openclaw-btn" href="{_oclaw_href}" target="_blank" rel="noopener">🤖 OpenClaw AI Chat</a>
    """, unsafe_allow_html=True)
    st.sidebar.markdown("---")

    # ── Dataset selection (sidebar) ───────────────────────────────────────
    st.sidebar.header("Dataset Selection")
    dataset_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.isdir(dataset_dir):
        dataset_dir = os.path.dirname(__file__)

    outage_options, site_options = discover_datasets(dataset_dir)

    default_outage = 'df_cleaned.parquet' if 'df_cleaned.parquet' in outage_options else ('df_cleaned.csv' if 'df_cleaned.csv' in outage_options else outage_options[0])
    selected_outage_name = st.sidebar.selectbox(
        "Select outages dataset", outage_options,
        index=outage_options.index(default_outage),
    )
    selected_outage_file = os.path.join(dataset_dir, selected_outage_name)

    selected_site_name = st.sidebar.selectbox(
        "Select chargepoints dataset", site_options,
        index=site_options.index('all_charging_sites.csv') if 'all_charging_sites.csv' in site_options else 0,
    )
    selected_site_file = os.path.join(dataset_dir, selected_site_name)

    # ── Load data (fetch from API if file missing) ────────────────────────
    t0 = time.time()
    if not os.path.exists(selected_outage_file):
        try:
            from data.fetch_outages import run_daily_fetch
            # Show loading in sidebar instead of full page
            fetch_status = st.sidebar.empty()
            fetch_status.info("📥 Downloading outage data...")
            result = run_daily_fetch()
            if result.get("error"):
                fetch_status.error(f"❌ Fetch failed: {result['error']}")
                st.error(f"Could not fetch outage data: {result['error']}")
                return
            fetch_status.success("✅ Data downloaded!")
            load_data.clear()
        except (ImportError, Exception) as e:
            st.error(f"Could not fetch outage data: {e}")
            return

    outage_mtime = os.path.getmtime(selected_outage_file) if os.path.exists(selected_outage_file) else 0
    site_mtime = os.path.getmtime(selected_site_file) if os.path.exists(selected_site_file) else 0
    charging_sites, outages = load_data(selected_outage_file, selected_site_file, outage_mtime, site_mtime)

    if charging_sites is None or outages is None:
        st.error("Failed to load data. Please check file paths.")
        return

    # ── Empty data guard: re-fetch if df_cleaned is empty ────────────────
    if outages.empty:
        st.warning("⚠️ Outage dataset is empty — re-fetching from API...")
        try:
            from data.fetch_outages import run_daily_fetch
            result = run_daily_fetch(full=True)
            if result.get("error"):
                st.error(f"Could not re-fetch outage data: {result['error']}")
                return
            load_data.clear()
            charging_sites, outages = load_data(selected_outage_file, selected_site_file, outage_mtime, site_mtime)
            if outages is None or outages.empty:
                st.error("Re-fetch returned empty data. Check the ENW API or API key.")
                return
        except (ImportError, Exception) as e:
            st.error(f"Could not re-fetch outage data: {e}")
            return

    t0 = _ts(f"load_data ({len(outages)} outages)", t0)

    # ── Flexibility tenders: fetch from API if missing or stale ──────────
    flex_geojson_path = os.path.join(dataset_dir, "flexibility_tenders.geojson")
    try:
        from advanced_charts.cache_utils import is_cache_stale
        from data.fetch_flexibility_tenders import run_flexibility_fetch
        if is_cache_stale(Path(flex_geojson_path)):
            fetch_status = st.sidebar.empty()
            fetch_status.caption("🔄 Refreshing flexibility tenders...")
            flex_result = run_flexibility_fetch()
            if flex_result.get("error"):
                fetch_status.warning(f"⚠️ Flex fetch: {flex_result['error']}")
            elif flex_result.get("fetched"):
                fetch_status.success("✅ Flexibility tenders updated")
            else:
                fetch_status.empty()
    except (ImportError, Exception):
        pass  # graceful — continue with whatever file exists

    flex_mtime = os.path.getmtime(flex_geojson_path) if os.path.exists(flex_geojson_path) else 0
    flex_result = load_flexibility_tenders(flex_geojson_path, flex_mtime)
    flex_gdf = flex_result[0] if flex_result else None
    flex_grouped = flex_result[1] if flex_result else None
    t0 = _ts("load_flexibility_tenders", t0)

    # ── Sidebar controls ──────────────────────────────────────────────────
    filters = render_sidebar(charging_sites, outages)
    t0 = _ts("render_sidebar", t0)

    # ── Auto-refresh and periodic fetch ───────────────────────────────────
    setup_autorefresh(filters["refresh_interval_min"], filters["show_live_incidents"], filters["live_refresh_min"])
    maybe_fetch_outage_data(filters["refresh_interval_min"])

    # ── Compute everything (with caching) ─────────────────────────────────
    # Create a hash of current filters to detect changes
    filter_hash = hash(str(sorted(filters.items())))

    # Only recompute if filters changed or first load
    if "cached_data" not in st.session_state or st.session_state.get("last_filter_hash") != filter_hash:
        with st.spinner("Computing risk predictions..."):
            data = prepare_app_data(selected_outage_file, selected_site_file, filters)
        st.session_state.cached_data = data
        st.session_state.last_filter_hash = filter_hash
        print("[CACHE] Recomputed data (filters changed)")
    else:
        data = st.session_state.cached_data
        print("[CACHE] Using cached data (no filter change)")
    
    t0 = _ts("prepare_app_data", t0)
    if data is None:
        st.error("Failed to prepare data.")
        return

    # ── Layout ────────────────────────────────────────────────────────────
    _ts(f"TOTAL main()", t_main)
    col1, col2 = st.columns([4, 1])

    with col1:
        st.subheader("Interactive Spatial Analysis")

        # Create map with pin (if previously clicked)
        interactive_map = create_advanced_map(
            data["charging_sites"], data["filtered_outages"],
            show_chargepoints=filters["show_chargepoints"],
            show_buffers=filters["show_buffers"],
            show_heatmap=filters["show_heatmap"],
            selected_categories=filters["selected_categories"],
            live_incidents=data["live_incidents"],
            risk_predictions=data["risk_predictions"],
            show_risk_heatmap=filters["show_risk_heatmap"],
            confidence_threshold=filters.get("confidence_threshold", 0.5),
            risk_report=data["risk_report"],
            clicked_lat=st.session_state.get("pin_lat"),
            clicked_lng=st.session_state.get("pin_lng"),
            clicked_site_name=st.session_state.get("selected_site"),
            flexibility_tenders=flex_gdf,
        )

        # Render map
        map_data = st_folium(
            interactive_map,
            use_container_width=True,
            height=600,
            returned_objects=["last_clicked", "last_object_clicked", "last_object_clicked_popup"],
            key="main_map",
        )

        # DEBUG: dump full map_data to see what st_folium returns
        print(f"[DEBUG] map_data keys: {list(map_data.keys()) if map_data else 'None'}")
        for k, v in (map_data or {}).items():
            print(f"[DEBUG]   {k}: {v}")

        # Process click — st_folium returns last_clicked for empty-map clicks
        # and last_object_clicked for marker clicks (last_clicked is None then)
        last_clicked = map_data.get('last_clicked')
        last_object = map_data.get('last_object_clicked')
        popup_html = map_data.get('last_object_clicked_popup')

        print(f"[INFO-SECTION] last_clicked: {last_clicked is not None}")
        print(f"[INFO-SECTION] last_object: {last_object is not None}")
        print(f"[INFO-SECTION] popup_html type: {type(popup_html)}, value: {repr(popup_html)[:200]}")
        print(f"[INFO-SECTION] session pin_lat: {st.session_state.get('pin_lat')}")
        print(f"[INFO-SECTION] session selected_site: {st.session_state.get('selected_site')}")

        # ── Flexibility tender click detection ───────────────────────────
        _is_flex_click = popup_html and 'class="flex-tender"' in str(popup_html)
        if _is_flex_click:
            import re
            _m = re.search(r'data-substation="([^"]+)"', str(popup_html))
            if _m:
                _clicked_sub = _m.group(1)
                if _clicked_sub != st.session_state.flex_selected_substation:
                    st.session_state.flex_selected_substation = _clicked_sub
                    st.session_state.flex_page_index = 0
                    # Clear chargepoint selection
                    st.session_state.pin_lat = None
                    st.session_state.pin_lng = None
                    st.session_state.selected_site = None
                    st.session_state.last_popup_html = popup_html
                    print(f"[FLEX-CLICK] Selected substation: {_clicked_sub}")
                    st.rerun()

        if last_clicked or last_object:
            # Get coords from whichever is available
            if last_object:
                click_lat = last_object['lat']
                click_lng = last_object['lng']
            else:
                click_lat = last_clicked['lat']
                click_lng = last_clicked['lng']

            # Track if this is a new click (avoid reprocessing same click)
            current_click = (round(click_lat, 6), round(click_lng, 6))
            last_processed = st.session_state.get("last_processed_click")

            print(f"[CLICK-DEBUG] current_click: {current_click}, last_processed: {last_processed}")

            if current_click != last_processed:
                st.session_state.last_processed_click = current_click

                result = process_map_click(map_data, data["charging_sites"])

                if result:
                    st.session_state.pin_lat = result['pin_lat']
                    st.session_state.pin_lng = result['pin_lng']
                    st.session_state.selected_site = result['selected_site']
                    # Clear flexibility tender selection when clicking elsewhere
                    st.session_state.flex_selected_substation = None
                    st.session_state.flex_page_index = 0
                    # Persist popup HTML across reruns; clear when clicking blank spot
                    if popup_html:
                        st.session_state.last_popup_html = popup_html
                    else:
                        st.session_state.last_popup_html = None
                    print(f"[CLICK] {'Chargepoint' if result['is_chargepoint'] else 'Location'}: {result['selected_site']}")
                    print(f"[CLICK] popup_html saved: {repr(popup_html)[:200]}")

                # Force rerun so map re-renders with pin
                st.rerun()

        # ── Info section — mirrors the map popup content ────────────────
        # Use live popup_html from map_data, fall back to persisted session state
        effective_popup = popup_html or st.session_state.get("last_popup_html")
        print(f"[INFO-SECTION] effective_popup: {repr(effective_popup)[:200]}")
        print(f"[INFO-SECTION] will render: {bool(effective_popup)}")

        if effective_popup:
            st.subheader("📍 Site Info")
            st.markdown(effective_popup, unsafe_allow_html=True)
        else:
            print("[INFO-SECTION] No popup to display — section skipped")

        # ── Flexibility Tender detail panel ──────────────────────────────
        if st.session_state.flex_selected_substation and flex_grouped:
            _sub = st.session_state.flex_selected_substation
            _records = flex_grouped.get(_sub, [])
            if _records:
                _total = len(_records)
                _idx = min(st.session_state.flex_page_index, _total - 1)
                _rec = _records[_idx]

                # Header with pagination arrows
                _hcol1, _hcol2, _hcol3 = st.columns([1, 6, 1])
                with _hcol1:
                    if st.button("◀", key="flex_prev"):
                        st.session_state.flex_page_index = (_idx - 1) % _total
                        st.rerun()
                with _hcol2:
                    st.markdown(
                        f"<h4 style='text-align:center; margin:0;'>{_sub} ({_idx + 1}/{_total})</h4>",
                        unsafe_allow_html=True,
                    )
                with _hcol3:
                    if st.button("▶", key="flex_next"):
                        st.session_state.flex_page_index = (_idx + 1) % _total
                        st.rerun()

                # Detail fields in a fixed-height scrollable container
                _fields = [
                    ("Substation Name", "substation_name"),
                    ("Post Codes", "post_codes"),
                    ("Voltage of connection (kV)", "voltage_of_connection_kv"),
                    ("Maximum requirement (MVA)", "maximum_requirement_mva"),
                    ("Need Type", "need_type"),
                    ("Delivery start date", "delivery_start_date"),
                    ("Months Required", "months_required"),
                    ("Times required", "times_required"),
                    ("Days required", "days_required"),
                    ("Maximum Utilisation Price (£/MWh)", "maximum_utilisation_price_mw"),
                    ("Estimated availability hours", "estimated_availability_hours"),
                    ("Estimated utilisation hours", "estimated_utilisation_hours"),
                    ("Easting", "easting"),
                    ("Northing", "northing"),
                    ("Lat", "lat"),
                    ("Long", "long"),
                    ("Period", "period"),
                    ("Site Number", "site_number"),
                    ("Ceiling Price (£/Period)", "ceiling_price_period"),
                ]

                _rows = ""
                for _label, _key in _fields:
                    _val = _rec.get(_key)
                    if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                        _val = "—"
                    _rows += f"<tr><td style='font-weight:600; padding:4px 8px; white-space:nowrap;'>{_label}</td><td style='padding:4px 8px;'>{_val}</td></tr>"

                st.markdown(
                    f"""
                    <div style="max-height:400px; overflow-y:auto; border:1px solid #e0e0e0; border-radius:6px; padding:4px;">
                        <table style="width:100%; font-size:0.9em; border-collapse:collapse;">
                            {_rows}
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Show selected site and charts
        if st.session_state.get("selected_site"):
            st.success(f"**{st.session_state.selected_site}**")
            display_dynamic_charts(
                st.session_state.selected_site,
                data["charging_sites"], data["filtered_outages"],
                is_dark=data["is_dark"],
                risk_predictions=data["risk_predictions"],
                risk_model_choice=filters["risk_model_choice"],
                clicked_lat=st.session_state.get("pin_lat"),
                clicked_lng=st.session_state.get("pin_lng"),
            )

    with col2:
        # ── Right panel: Dashboard ───────────────────────────────────────
        render_live_incidents(data["live_incidents"], filters["show_live_incidents"], filters["live_refresh_label"])
        render_ai_dashboard(
            data["filtered_outages"], data["outages"], filters["years"],
            data["charging_sites"], filters["selected_categories"],
            data["risk_report"], data["risk_predictions"],
        )


if __name__ == "__main__":
    main()
