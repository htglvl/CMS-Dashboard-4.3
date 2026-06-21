"""Tab 2: Customer Impact — pie charts of impact and frequency by duration."""

import streamlit as st


def render_customer_impact(chart_generator, site_outages, site_name):
    """Render two side-by-side pie charts with help tooltips."""
    col1, col2 = st.columns(2)

    with col1:
        st.caption(
            "Customer Impact by Duration",
            help="What proportion of total customer-hours lost comes from short vs long outages. "
                 "Reveals whether long outages are driving most of the impact.",
        )
        impact_pie = chart_generator.create_duration_impact_pie(site_outages, site_name)
        st.plotly_chart(impact_pie, width='stretch')

    with col2:
        st.caption(
            "Outage Frequency by Duration",
            help="What proportion of outages fall into each duration bucket. "
                 "Shows if most outages are short or long.",
        )
        freq_pie = chart_generator.create_duration_frequency_pie(site_outages, site_name)
        st.plotly_chart(freq_pie, width='stretch')
