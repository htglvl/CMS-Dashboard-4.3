"""Dynamic chart display when a site is clicked on the map.

This module is the orchestrator — it creates the tabs and delegates
rendering to the sub-modules in ``dashboard/charts/``.
"""

import time
import streamlit as st
from advanced_charts import DynamicChartGenerator

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


def display_dynamic_charts(site_name, charging_sites, filtered_outages, is_dark=False, risk_predictions=None, risk_model_choice="Random Forest"):
    """Display dynamic charts based on selected site."""

    t_total = time.time()
    print(f"\n=== Detailed Analysis: {site_name} ===")

    t0 = time.time()
    chart_generator = _get_chart_generator(filtered_outages, charging_sites)
    t0 = _ts("Chart generator (cached)", t0)

    t_inner = time.time()
    site_outages, site_info = chart_generator.get_site_specific_data(site_name)
    _ts(f"  get_site_outages ({len(site_outages)} outages)", t_inner)
    t0 = _ts(f"get_site_specific_data total", t0)

    st.markdown(f"## Detailed Analysis: **{site_name}**")

    render_site_summary(site_outages, site_info)
    t0 = _ts("Site summary", t0)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Frequency Timeline",
        "Customer Impact",
        "Risk Assessment",
        "Insights",
        "Risk Prediction",
    ])

    with tab1:
        render_frequency_timeline(chart_generator, site_outages, site_name)
        t0 = _ts("Tab 1: Frequency Timeline", t0)

    with tab2:
        render_customer_impact(chart_generator, site_outages, site_name)
        t0 = _ts("Tab 2: Customer Impact", t0)

    with tab3:
        render_risk_assessment(chart_generator, site_name)
        t0 = _ts("Tab 3: Risk Assessment", t0)

    with tab4:
        render_rule_insights(site_outages, site_info)
        t0 = _ts("Tab 4: Rule Insights", t0)

    with tab5:
        render_risk_prediction(site_outages, site_info, risk_predictions, risk_model_choice)
        t0 = _ts("Tab 5: Risk Prediction", t0)

    _ts(f"TOTAL", t_total)
