"""Tab 3: Risk Assessment — radar chart and vulnerability score."""

import streamlit as st


def render_risk_assessment(chart_generator, site_name):
    """Render the radar chart, overall score, and interpretation guide."""
    # Check if this is a custom location (not in charging sites)
    is_custom = site_name.startswith("📍 Location")

    if is_custom:
        st.info("Risk assessment radar chart not available for custom locations. See Risk Prediction tab for details.")
        st.markdown(
            """
            **Why?** The risk assessment compares this location against all charging sites.
            Custom locations don't have historical site-specific data for comparison.

            **What's available:**
            - Risk Prediction tab shows ML-based risk for this location
            - Customer Impact shows nearby outage data
            - Insights show patterns in the area
            """
        )
        return

    try:
        risk_chart = chart_generator.create_risk_assessment_chart(site_name)
        st.plotly_chart(risk_chart, width='stretch')

        scores = chart_generator.get_risk_scores(site_name)
        if scores:
            overall = scores.get('Overall Score', 0)
            st.markdown(f"**Overall Vulnerability Score:** {overall:.1f}/100")
            st.markdown(
                """
                This combined score is the average of the Frequency, Duration, Impact
                and Consistency metrics. Scores are normalised to a 0-100 scale
                across all sites currently loaded. A higher score indicates a site
                that is more vulnerable to outages (frequent, long, high impact or
                highly variable), whereas a lower score suggests greater stability
                and predictability.
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
