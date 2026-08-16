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


def display_dynamic_charts(site_name, charging_sites, filtered_outages, is_dark=False, risk_predictions=None, risk_model_choice="Random Forest", clicked_lat=None, clicked_lng=None, flex_selected_substation=None, flex_grouped=None, monthly_selected_substation=None, monthly_grouped=None):
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

    # ── Build tab list (conditionally prepend Region Info tabs) ─────────
    _has_flex = bool(flex_selected_substation and flex_grouped)
    _has_monthly = bool(monthly_selected_substation and monthly_grouped)
    print(f"[TENDER-TAB] biannual={flex_selected_substation}, monthly={monthly_selected_substation}")

    _tab_names = ["Frequency Timeline", "Customer Impact",
                  "Risk Assessment", "Insights", "Risk Prediction"]
    if _has_flex:
        _tab_names.insert(0, "Biannual Region Info")
    if _has_monthly:
        _tab_names.insert(0 if _has_flex else 0, "Monthly Region Info")

    _tabs = st.tabs(_tab_names)

    # Map tabs by name for robustness
    _tab_map = {name: tab for name, tab in zip(_tab_names, _tabs)}
    _tab_freq = _tab_map["Frequency Timeline"]
    _tab_cust = _tab_map["Customer Impact"]
    _tab_risk = _tab_map["Risk Assessment"]
    _tab_insg = _tab_map["Insights"]
    _tab_pred = _tab_map["Risk Prediction"]

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

    # ── Region Info tabs (tender detail) ───────────────────────────────
    _REGION_FIELDS = [
        ("Substation Name", "substation_name"),
        ("Post Codes", "post_codes"),
        ("Voltage of connection (kV)", "voltage_of_connection_kv"),
        ("Maximum requirement (MVA)", "maximum_requirement_mva"),
        ("Easting", "easting"),
        ("Northing", "northing"),
        ("Lat", "lat"),
        ("Long", "long"),
    ]
    _CONTRACT_FIELDS = [
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

    def _render_region_tab(tab, records, label):
        """Render shared region info + contract sub-tabs inside *tab*."""
        with tab:
            if not records:
                st.info(f"No contract records found for this {label} substation.")
                return
            _rec0 = records[0]
            _region_rows = ""
            for _label, _key in _REGION_FIELDS:
                _val = _rec0.get(_key)
                if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                    _val = "—"
                _region_rows += (
                    f"<tr><td style='font-weight:600; padding:4px 8px; white-space:nowrap;'>{_label}</td>"
                    f"<td style='padding:4px 8px;'>{_val}</td></tr>"
                )
            st.markdown(
                f"""<div style="border:1px solid #e0e0e0; border-radius:6px; padding:4px; margin-bottom:12px;">
                    <table style="width:100%; font-size:0.9em; border-collapse:collapse;">{_region_rows}</table>
                </div>""",
                unsafe_allow_html=True,
            )
            _contract_tab_names = [
                f"{r.get('need_type', '—')} | {r.get('delivery_start_date', '—')} | {r.get('period', '—')}"
                for r in records
            ]
            _contract_tabs = st.tabs(_contract_tab_names)
            for _ctab, _rec in zip(_contract_tabs, records):
                with _ctab:
                    _contract_rows = ""
                    for _label, _key in _CONTRACT_FIELDS:
                        _val = _rec.get(_key)
                        if _val is None or (isinstance(_val, float) and pd.isna(_val)):
                            _val = "—"
                        _contract_rows += (
                            f"<tr><td style='font-weight:600; padding:4px 8px; white-space:nowrap;'>{_label}</td>"
                            f"<td style='padding:4px 8px;'>{_val}</td></tr>"
                        )
                    st.markdown(
                        f"""<div style="max-height:400px; overflow-y:auto; border:1px solid #e0e0e0; border-radius:6px; padding:4px;">
                            <table style="width:100%; font-size:0.9em; border-collapse:collapse;">{_contract_rows}</table>
                        </div>""",
                        unsafe_allow_html=True,
                    )

    if _has_flex:
        _render_region_tab(
            _tab_map["Biannual Region Info"],
            flex_grouped.get(flex_selected_substation, []),
            "biannual",
        )
    if _has_monthly:
        _render_region_tab(
            _tab_map["Monthly Region Info"],
            monthly_grouped.get(monthly_selected_substation, []),
            "monthly",
        )

    _ts(f"TOTAL", t_total)
