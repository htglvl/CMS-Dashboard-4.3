"""Tab 3: Risk Assessment — radar chart and vulnerability score."""

import streamlit as st


def render_risk_assessment(chart_generator, site_name):
    """Render the radar chart, overall score, and interpretation guide."""
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
