"""Tab 1: Frequency Timeline — outage count and customer-hours over time."""

import streamlit as st


def render_frequency_timeline(chart_generator, site_outages, site_name):
    """Render two side-by-side line charts with help tooltips."""
    # Sanitize site_name for use as key
    safe_key = "".join(c for c in str(site_name) if c.isalnum())[:20]

    col1, col2 = st.columns(2)

    with col1:
        st.caption(
            "Outage Frequency by Duration",
            help="Outage count per month, split by duration category "
                 "(e.g. < 3 hours, 3-6 hours, 6-12 hours, > 12 hours). "
                 "Shows how often outages happen over time and whether they're getting more frequent.",
        )
        freq_chart = chart_generator.create_frequency_timeline(site_outages, site_name)
        st.plotly_chart(freq_chart, use_container_width=True, key=f"freq_{safe_key}")

    with col2:
        st.caption(
            "Customer Hours Lost Over Time",
            help="Average customer-hours lost per month. "
                 "Shows the trend of impact severity over time.",
        )
        hours_chart = chart_generator.create_customer_hours_timeline(site_outages, site_name)
        st.plotly_chart(hours_chart, use_container_width=True, key=f"hours_{safe_key}")
