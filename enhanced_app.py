"""
CMS Grid Resilience AI Dashboard — main entry point.

This file handles page configuration, CSS, and UI rendering only.
All data logic lives in ``dashboard/app_logic.py``.
"""

import os
import time
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from dashboard.app_logic import discover_datasets, prepare_app_data, load_data
from dashboard.sidebar import render_sidebar, setup_autorefresh, maybe_fetch_outage_data
from dashboard.map import create_advanced_map
from dashboard.chart_display import display_dynamic_charts
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

/* Make spinner only show in its container, not full page */
.stSpinner > div {
    position: relative !important;
}

/* Remove grey overlay from spinner */
.stSpinner::before {
    display: none !important;
}

/* Style the spinner to be compact */
.stSpinner > div > div {
    border-width: 3px !important;
    width: 24px !important;
    height: 24px !important;
}
</style>
""", unsafe_allow_html=True)


def _ts(msg, t0):
    """Print a timing line to console and return current time."""
    t1 = time.time()
    print(f"  [{(t1-t0)*1000:7.1f}ms] {msg}")
    return t1


def _render_ai_chat(risk_predictions, outages, charging_sites):
    """Render the AI chat interface using Streamlit chat components."""
    from advanced_charts.recommendation_engine import RecommendationEngine

    # Initialize session state
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Welcome message if no messages yet
    if not st.session_state.chat_messages:
        st.markdown("""
        <div style="text-align: center; padding: 20px; color: #666;">
            <p style="font-size: 40px; margin-bottom: 10px;">🤖</p>
            <p style="font-weight: bold; margin-bottom: 15px;">Ask the AI about:</p>
            <ul style="text-align: left; display: inline-block;">
                <li>Outage risk areas</li>
                <li>Charger placement</li>
                <li>Community impact</li>
                <li>Investment priorities</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    # Display existing messages
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask about risk, chargers, or community impact...", key="ai_chat_tab"):
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get AI response with typing indicator
        with st.chat_message("assistant"):
            # Show typing indicator
            typing_placeholder = st.empty()
            typing_placeholder.markdown("🤖 *Thinking...*")

            engine = RecommendationEngine(risk_predictions, outages, charging_sites)
            response = engine.ask(prompt)

            # Replace typing indicator with response
            typing_placeholder.empty()
            st.markdown(response)

        # Add response to history
        st.session_state.chat_messages.append({"role": "assistant", "content": response})
        st.rerun()

    # Clear button
    if st.session_state.chat_messages:
        st.markdown("---")
        if st.button("🗑️ Clear Chat", key="clear_chat_tab"):
            st.session_state.chat_messages = []
            st.rerun()


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

    st.markdown('<h1 class="main-header">CMS Grid Resilience AI Dashboard</h1>', unsafe_allow_html=True)

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
    t0 = _ts(f"load_data ({len(outages)} outages)", t0)

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

        # Get pin coordinates from session state
        pin_lat = st.session_state.get("pin_lat")
        pin_lng = st.session_state.get("pin_lng")
        selected_site = st.session_state.get("selected_site")

        # Debug: Print pin coordinates
        print(f"[DEBUG] Creating map with pin_lat={pin_lat}, pin_lng={pin_lng}")

        # Create map with pin at clicked location
        interactive_map = create_advanced_map(
            data["charging_sites"], data["filtered_outages"],
            show_chargepoints=filters["show_chargepoints"],
            show_buffers=filters["show_buffers"],
            show_heatmap=filters["show_heatmap"],
            selected_categories=filters["selected_categories"],
            live_incidents=data["live_incidents"],
            risk_predictions=data["risk_predictions"],
            show_risk_heatmap=filters["show_risk_heatmap"],
            risk_report=data["risk_report"],
            clicked_lat=pin_lat,
            clicked_lng=pin_lng,
            clicked_site_name=selected_site,
        )

        # Render map and capture click
        map_data = st_folium(
            interactive_map,
            use_container_width=True,
            height=600,
            returned_objects=["last_clicked"],
            key="main_map",
        )

        # Store clicked coordinates
        if map_data.get('last_clicked'):
            clicked_lat = map_data['last_clicked']['lat']
            clicked_lng = map_data['last_clicked']['lng']
            st.session_state.pin_lat = clicked_lat
            st.session_state.pin_lng = clicked_lng
            st.session_state.selected_site = f"📍 Location ({clicked_lat:.4f}, {clicked_lng:.4f})"
            print(f"[DEBUG] Click detected: pin_lat={clicked_lat}, pin_lng={clicked_lng}")

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
        # ── Right panel with tabs: Dashboard / AI Chat ────────────────────
        tab_dashboard, tab_chat = st.tabs(["📊 Dashboard", "🤖 AI Chat"])

        with tab_dashboard:
            render_live_incidents(data["live_incidents"], filters["show_live_incidents"], filters["live_refresh_label"])
            render_ai_dashboard(
                data["filtered_outages"], data["outages"], filters["years"],
                data["charging_sites"], filters["selected_categories"],
                data["risk_report"], data["risk_predictions"],
            )

        with tab_chat:
            _render_ai_chat(data["risk_predictions"], data["outages"], data["charging_sites"])


if __name__ == "__main__":
    main()
