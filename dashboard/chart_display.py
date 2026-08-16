"""Dynamic chart display when a site is clicked on the map.

This module is the orchestrator — it creates the tabs and delegates
rendering to the sub-modules in ``dashboard/charts/``.
"""

import time
import numpy as np
import pandas as pd
import streamlit as st
from advanced_charts import DynamicChartGenerator
from advanced_charts.data import outages_within_radius

from dashboard.charts.site_summary import render_site_summary
from dashboard.charts.frequency_timeline import render_frequency_timeline
from dashboard.charts.customer_impact import render_customer_impact
from dashboard.charts.risk_assessment import render_risk_assessment
from dashboard.charts.rule_insights import render_rule_insights
from dashboard.charts.risk_prediction import render_risk_prediction


def _get_chart_generator(outages_df, sites_df):
    """Create a DynamicChartGenerator backed by the precomputed cache.

    No @st.cache_resource needed — SiteData loads from the pickle cache
    in sub-millisecond time, so constructing a new instance is cheaper
    than hashing a 300K-row DataFrame.
    """
    return DynamicChartGenerator(outages_df, sites_df)


def _ts(msg, t0):
    """Print a timing line to console and return current time."""
    t1 = time.time()
    print(f"  [{(t1-t0)*1000:7.1f}ms] {msg}")
    return t1


def display_dynamic_charts(site_name, charging_sites, filtered_outages, is_dark=False, risk_predictions=None, risk_model_choice="Random Forest", clicked_lat=None, clicked_lng=None, flex_selected_substation=None, flex_grouped=None):
    """Display dynamic charts based on selected site."""

    t_total = time.time()
    print(f"\n=== Detailed Analysis: {site_name} ===")

    t0 = time.time()
    chart_generator = _get_chart_generator(filtered_outages, charging_sites)
    t0 = _ts("Chart generator (cached)", t0)

    # Check if site_name is a valid charging site
    is_custom_location = site_name.startswith("📍 Location")

    if is_custom_location and clicked_lat is not None and clicked_lng is not None:
        # Custom location - create fake site_info with clicked coordinates
        site_info = pd.Series({
            'charge_point_location': site_name,
            'latitude': clicked_lat,
            'longitude': clicked_lng,
            'site_category': 'Custom Location'
        })
        # Find outages near clicked location (same 2-mile radius as chargepoints)
        site_outages = outages_within_radius(filtered_outages, clicked_lat, clicked_lng)
    else:
        # Valid charging site
        t_inner = time.time()
        site_outages, site_info = chart_generator.get_site_specific_data(site_name)
        _ts(f"  get_site_outages ({len(site_outages)} outages)", t_inner)
        t0 = _ts("get_site_specific_data total", t0)

    st.markdown(f"## Detailed Analysis: **{site_name}**")

    render_site_summary(site_outages, site_info)
    t0 = _ts("Site summary", t0)

    # ── Build tab list (conditionally prepend Region Info) ──────────────
    _has_flex = bool(flex_selected_substation and flex_grouped)
    print(f"[FLEX-TAB] flex_selected_substation={flex_selected_substation}, flex_grouped={flex_grouped is not None}, _has_flex={_has_flex}")
    _tab_names = (
        ["Region Info", "Frequency Timeline", "Customer Impact",
         "Risk Assessment", "Insights", "Risk Prediction"]
        if _has_flex
        else ["Frequency Timeline", "Customer Impact",
              "Risk Assessment", "Insights", "Risk Prediction"]
    )
    _tabs = st.tabs(_tab_names)

    if _has_flex:
        _tab_flex = _tabs[0]
        _tab_freq = _tabs[1]
        _tab_cust = _tabs[2]
        _tab_risk = _tabs[3]
        _tab_insg = _tabs[4]
        _tab_pred = _tabs[5]
    else:
        _tab_freq = _tabs[0]
        _tab_cust = _tabs[1]
        _tab_risk = _tabs[2]
        _tab_insg = _tabs[3]
        _tab_pred = _tabs[4]

    with _tab_freq:
        render_frequency_timeline(chart_generator, site_outages, site_name)
        t0 = _ts("Tab: Frequency Timeline", t0)

    with _tab_cust:
        render_customer_impact(chart_generator, site_outages, site_name)
        t0 = _ts("Tab: Customer Impact", t0)

    with _tab_risk:
        render_risk_assessment(chart_generator, site_name)
        t0 = _ts("Tab: Risk Assessment", t0)

    with _tab_insg:
        render_rule_insights(site_outages, site_info)
        t0 = _ts("Tab: Rule Insights", t0)

    with _tab_pred:
        render_risk_prediction(site_outages, site_info, risk_predictions, risk_model_choice, clicked_lat, clicked_lng)
        t0 = _ts("Tab: Risk Prediction", t0)

    # ── Region Info tab (flexibility tender detail) ────────────────────
    if _has_flex:
        with _tab_flex:
            _sub = flex_selected_substation
            _records = flex_grouped.get(_sub, [])
            print(f"[FLEX-TAB] Rendering Region Info for substation={_sub}, records={len(_records)}")
            if _records:
                _total = len(_records)

                # Overall region info (shared across all contracts — from first record)
                _rec0 = _records[0]
                _region_fields = [
                    ("Substation Name", "substation_name"),
                    ("Post Codes", "post_codes"),
                    ("Voltage of connection (kV)", "voltage_of_connection_kv"),
                    ("Maximum requirement (MVA)", "maximum_requirement_mva"),
                    ("Easting", "easting"),
                    ("Northing", "northing"),
                    ("Lat", "lat"),
                    ("Long", "long"),
                ]
                _region_rows = ""
                for _label, _key in _region_fields:
                    _val = _rec0.get(_key)
                    if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                        _val = "—"
                    _region_rows += (
                        f"<tr><td style='font-weight:600; padding:4px 8px; white-space:nowrap;'>{_label}</td>"
                        f"<td style='padding:4px 8px;'>{_val}</td></tr>"
                    )

                st.markdown(
                    f"""
                    <div style="border:1px solid #e0e0e0; border-radius:6px; padding:4px; margin-bottom:12px;">
                        <table style="width:100%; font-size:0.9em; border-collapse:collapse;">
                            {_region_rows}
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Each contract as a sub-tab (no rerun on switch)
                _contract_tab_names = [
                    f"{r.get('need_type', '—')} | {r.get('delivery_start_date', '—')} | {r.get('period', '—')}"
                    for r in _records
                ]
                _contract_tabs = st.tabs(_contract_tab_names)

                for _i, (_ctab, _rec) in enumerate(zip(_contract_tabs, _records)):
                    with _ctab:
                        _contract_fields = [
                            ("Need Type", "need_type"),
                            ("Delivery start date", "delivery_start_date"),
                            ("Months Required", "months_required"),
                            ("Times required", "times_required"),
                            ("Days required", "days_required"),
                            ("Maximum Utilisation Price (£/MWh)", "maximum_utilisation_price_mw"),
                            ("Estimated availability hours", "estimated_availability_hours"),
                            ("Estimated utilisation hours", "estimated_utilisation_hours"),
                            ("Period", "period"),
                            ("Site Number", "site_number"),
                            ("Ceiling Price (£/Period)", "ceiling_price_period"),
                        ]

                        _contract_rows = ""
                        for _label, _key in _contract_fields:
                            _val = _rec.get(_key)
                            if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                                _val = "—"
                            _contract_rows += (
                                f"<tr><td style='font-weight:600; padding:4px 8px; white-space:nowrap;'>{_label}</td>"
                                f"<td style='padding:4px 8px;'>{_val}</td></tr>"
                            )

                        st.markdown(
                            f"""
                            <div style="max-height:400px; overflow-y:auto; border:1px solid #e0e0e0; border-radius:6px; padding:4px;">
                                <table style="width:100%; font-size:0.9em; border-collapse:collapse;">
                                    {_contract_rows}
                                </table>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
            else:
                st.info("No contract records found for this substation.")

    _ts(f"TOTAL", t_total)
