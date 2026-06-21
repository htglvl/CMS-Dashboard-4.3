"""Tab 4: Rule-based Insights — threshold-driven risk classification."""

import streamlit as st
from advanced_charts import AIRecommendationEngine


def render_rule_insights(site_outages, site_info):
    """Render risk level, recommendations, and key metrics."""
    ai_analysis = AIRecommendationEngine.analyze_site_performance(site_outages, site_info)

    st.markdown("Rule-based Insights")

    risk_level = ai_analysis['risk_level']
    st.markdown(f"**Risk Level:** {risk_level}")

    st.markdown("**Recommendations:**")
    for rec in ai_analysis['recommendations']:
        st.markdown(f"• {rec}")

    if ai_analysis['key_insights']:
        st.markdown("Key Metrics:")
        insights = ai_analysis['key_insights']
        for key, value in insights.items():
            if isinstance(value, (int, float)):
                st.markdown(f"• **{key.replace('_', ' ').title()}:** {value:,.1f}")
            else:
                st.markdown(f"• **{key.replace('_', ' ').title()}:** {value}")
