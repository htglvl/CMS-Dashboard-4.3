"""Advanced charts package — data access, chart factories, and recommendations.

Sub-modules
-----------
* ``data`` — ``SiteData`` class for data access and risk scoring.
* ``charts`` — standalone Plotly chart factory functions.
* ``recommendations`` — ``AIRecommendationEngine`` for rule-based insights.

Backward compatibility
----------------------
``DynamicChartGenerator`` is preserved as a thin wrapper that delegates
to ``SiteData`` (data layer) and the chart factory functions.  Existing
code that uses ``DynamicChartGenerator`` continues to work unchanged.
"""

import pandas as pd

from advanced_charts.data import SiteData
from advanced_charts.charts import (
    create_frequency_timeline,
    create_customer_hours_timeline,
    create_duration_impact_pie,
    create_duration_frequency_pie,
    create_risk_assessment_chart,
)
from advanced_charts.recommendations import AIRecommendationEngine


class DynamicChartGenerator:
    """Backward-compatible wrapper around ``SiteData`` + chart factories.

    Usage::

        gen = DynamicChartGenerator(outages, sites)
        site_outages, site_info = gen.get_site_specific_data("My Site")
        fig = gen.create_frequency_timeline(site_outages, "My Site")
        scores = gen.get_risk_scores("My Site")
    """

    def __init__(self, outages_data: pd.DataFrame, charging_sites_data: pd.DataFrame):
        self._data = SiteData(outages_data, charging_sites_data)

    # -- Data access (delegates to SiteData) --------------------------------

    def get_site_specific_data(self, site_name: str, buffer_radius_km: float = 3.218):
        """Return outages within *buffer_radius_km* of *site_name* and the site row."""
        return self._data.get_site_outages(site_name, buffer_radius_km)

    def get_risk_scores(self, site_name: str) -> dict:
        """Return normalised risk scores dict for *site_name*."""
        site_outages, _ = self._data.get_site_outages(site_name)
        return self._data.compute_risk_metrics(site_outages)

    # -- Chart factories (delegates to standalone functions) ----------------

    def create_frequency_timeline(self, site_outages: pd.DataFrame, site_name: str):
        return create_frequency_timeline(site_outages, site_name)

    def create_customer_hours_timeline(self, site_outages: pd.DataFrame, site_name: str):
        return create_customer_hours_timeline(site_outages, site_name)

    def create_duration_impact_pie(self, site_outages: pd.DataFrame, site_name: str):
        return create_duration_impact_pie(site_outages, site_name)

    def create_duration_frequency_pie(self, site_outages: pd.DataFrame, site_name: str):
        return create_duration_frequency_pie(site_outages, site_name)

    def create_risk_assessment_chart(self, site_name: str, is_dark: bool = False):
        site_outages, _ = self._data.get_site_outages(site_name)
        scores = self._data.compute_risk_metrics(site_outages)
        return create_risk_assessment_chart(site_outages, site_name, scores)


__all__ = [
    "SiteData",
    "DynamicChartGenerator",
    "AIRecommendationEngine",
    "create_frequency_timeline",
    "create_customer_hours_timeline",
    "create_duration_impact_pie",
    "create_duration_frequency_pie",
    "create_risk_assessment_chart",
]
