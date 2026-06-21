"""Detailed analysis chart sub-modules.

Each file corresponds to one tab in the site detail view.
"""

from dashboard.charts.site_summary import render_site_summary
from dashboard.charts.frequency_timeline import render_frequency_timeline
from dashboard.charts.customer_impact import render_customer_impact
from dashboard.charts.risk_assessment import render_risk_assessment
from dashboard.charts.rule_insights import render_rule_insights
from dashboard.charts.risk_prediction import render_risk_prediction

__all__ = [
    "render_site_summary",
    "render_frequency_timeline",
    "render_customer_impact",
    "render_risk_assessment",
    "render_rule_insights",
    "render_risk_prediction",
]
