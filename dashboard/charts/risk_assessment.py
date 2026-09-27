"""Tab 3: Risk Assessment — radar chart and vulnerability score."""

import streamlit as st


def render_risk_assessment(chart_generator, site_name, site_outages=None):
    """Render the radar chart, overall score, and interpretation guide."""
    is_custom = site_name.startswith("📍 Location")
    if is_custom and site_outages is None:
        st.info("Select a location on the map to assess its nearby outage history.")
        return
    if site_outages is not None and site_outages.empty:
        st.info("No recorded outages within 2 miles match the current filters. "
                "A historical risk score cannot be calculated; this does not establish that the location has no risk.")
        return

    try:
        if is_custom:
            st.caption(f"Based on {len(site_outages):,} recorded outages within 2 miles "
                       "of the selected location, using the current filters and the same "
                       "reference ranges as charging sites. This is an area assessment, "
                       "not a confirmed connection to a particular electricity supply.")
        risk_chart = chart_generator.create_risk_assessment_chart(site_name, site_outages=site_outages)
        st.plotly_chart(risk_chart, width='stretch')

        scores = chart_generator.get_risk_scores(site_name, site_outages=site_outages)
        if scores:
            overall = scores.get('Overall Score', 0)
            st.markdown(f"**Overall Vulnerability Score:** {overall:.1f}/100")
            st.markdown(
                """
                This combined score is the average of the Frequency, Duration, Impact
                and Consistency metrics. Scores are normalised to a 0-100 scale
                against the charging-site reference ranges and clipped to that scale.
                Frequency, duration and impact increase with greater outage burden;
                consistency increases with more predictable outage durations.
                This descriptive composite is not a probability of a future outage.
                """
            )

        st.markdown("Risk Assessment Interpretation")
        st.markdown(
            """
            - **Frequency Score**: Based on the number of outages (higher = more frequent)
            - **Duration Score**: Based on the average outage length (higher = longer outages)
            - **Impact Score**: Based on total customer hours affected (higher = more impact)
            - **Consistency Score**: Based on outage predictability (higher = more consistent patterns)
            """
        )
    except Exception as e:
        st.warning(f"Could not load risk assessment: {e}")
