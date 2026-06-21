"""Basic site info metrics row above the tabs."""

import streamlit as st


def render_site_summary(site_outages, site_info):
    """Render the 4-column metric row for the selected site."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        outage_count = len(site_outages)
        st.metric("Total Outages", f"{outage_count:,}")

    with col2:
        avg_duration = site_outages['duration-hours'].mean() if not site_outages.empty else 0
        st.metric("Avg Duration", f"{avg_duration:.1f}h")

    with col3:
        total_impact = (site_outages['Total Customer Minutes Lost'].sum() / 60) if not site_outages.empty else 0
        st.metric("Customer Hours Lost", f"{total_impact:,.0f}")

    with col4:
        category = site_info['site_category']
        if outage_count > 20:
            risk_desc = "High Risk"
        elif outage_count > 10:
            risk_desc = "Medium Risk"
        else:
            risk_desc = "Low Risk"
        st.metric("Site Category", f"{category} ({risk_desc})")
