"""Rule-based risk classification and recommendations."""

import pandas as pd


class AIRecommendationEngine:
    """Rule-based risk classification and recommendations."""

    @staticmethod
    def analyze_site_performance(site_outages: pd.DataFrame, site_info: pd.Series) -> dict:
        """Classify risk and generate recommendations for a site."""
        if site_outages.empty:
            return {
                'risk_level': 'Unknown',
                'recommendations': ['Insufficient data for analysis'],
                'key_insights': {},
            }

        total_outages = len(site_outages)
        avg_duration = site_outages['duration-hours'].mean()
        total_impact = site_outages['Total Customer Minutes Lost'].sum() / 60

        insights = {
            'total_outages': total_outages,
            'avg_duration': avg_duration,
            'total_customer_hours_lost': total_impact,
        }

        recommendations = []

        if total_outages > 20 and avg_duration > 8:
            risk_level = 'Critical'
            recommendations.append("Priority location for immediate V2X deployment")
            recommendations.append("Conduct detailed grid stability analysis")
        elif total_outages > 10 or avg_duration > 4:
            risk_level = 'High'
            recommendations.append("Recommended for V2X upgrade")
            recommendations.append("Consider backup power solutions")
        elif total_outages > 5:
            risk_level = 'Medium'
            recommendations.append("Monitor for trend changes")
            recommendations.append("Evaluate V2X cost-benefit")
        else:
            risk_level = 'Low'
            recommendations.append("Current infrastructure appears adequate")

        if site_info['site_category'] == 'V2X Chargepoint':
            recommendations.append("V2X capability can mitigate grid instability")
            insights['v2x_value'] = 'High - Already equipped for bidirectional power flow'
        else:
            recommendations.append("Consider V2X upgrade for grid support")
            insights['v2x_value'] = 'Potential - Retrofit could provide grid benefits'

        if 'month_name' in site_outages.columns:
            winter = site_outages[site_outages['month_name'].isin(['December', 'January', 'February'])]
            if len(winter) > len(site_outages) * 0.4:
                recommendations.append("High winter vulnerability - prioritize cold weather resilience")

        return {
            'risk_level': risk_level,
            'recommendations': recommendations,
            'key_insights': insights,
        }
