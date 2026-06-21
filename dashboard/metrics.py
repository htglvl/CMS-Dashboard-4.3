"""Metric cards, site distribution, quick insights, and AI recommendations."""

import pandas as pd
import plotly.express as px
import streamlit as st


def render_metric_cards(filtered_outages, outages, years):
    """Render month-over-month metric cards."""
    if filtered_outages.empty:
        st.info("No outage data available.")
        return

    # Ensure we have month column
    if 'month' not in filtered_outages.columns:
        if 'incident_date_time' in filtered_outages.columns:
            filtered_outages = filtered_outages.copy()
            # Convert to datetime and remove timezone info before converting to period
            dt_series = pd.to_datetime(filtered_outages['incident_date_time'], errors='coerce')
            if dt_series.dt.tz is not None:
                dt_series = dt_series.dt.tz_localize(None)
            filtered_outages['month'] = dt_series.dt.to_period('M')
        else:
            st.info("No date data available for comparison.")
            return

    # Get current and previous month
    months = filtered_outages['month'].dropna().unique()
    if len(months) < 2:
        # Not enough data for comparison
        curr = filtered_outages
        prev = pd.DataFrame()
        current_month_label = "current period"
        prev_month_label = "previous period"
    else:
        months_sorted = sorted(months)
        current_month = months_sorted[-1]
        prev_month = months_sorted[-2]
        current_month_label = str(current_month)
        prev_month_label = str(prev_month)

        curr = filtered_outages[filtered_outages['month'] == current_month]
        prev = filtered_outages[filtered_outages['month'] == prev_month]

    def _delta_pct(current_val, prev_val):
        if prev_val and prev_val > 0:
            pct = ((current_val - prev_val) / prev_val) * 100
            return f"{pct:+.1f}% vs {prev_month_label}"
        return None

    # 1. Customers affected
    curr_customers = curr['customer_affected'].sum() if not curr.empty else 0
    prev_customers = prev['customer_affected'].sum() if not prev.empty else 0
    st.metric(
        "Customers Affected", f"{curr_customers:,}",
        delta=_delta_pct(curr_customers, prev_customers), delta_color="inverse",
        help=f"Total customers affected by outages in {current_month_label}."
    )

    # 2. Customer hours lost
    curr_hours_lost = (curr['total_customer_minutes_lost'].sum() / 60) if not curr.empty else 0
    prev_hours_lost = (prev['total_customer_minutes_lost'].sum() / 60) if not prev.empty else 0
    st.metric(
        "Customer Hours Lost", f"{curr_hours_lost:,.0f}",
        delta=_delta_pct(curr_hours_lost, prev_hours_lost), delta_color="inverse",
        help=f"Total customer-hours of supply lost in {current_month_label}."
    )

    # 3. Median outage duration
    curr_median = curr['duration-hours'].median() if not curr.empty else 0
    prev_median = prev['duration-hours'].median() if not prev.empty else 0
    st.metric(
        "Median Outage Duration", f"{curr_median:.1f}h",
        delta=_delta_pct(curr_median, prev_median), delta_color="inverse",
        help="Median (not mean) duration — less skewed by extreme outages."
    )

    # 4. Most common cause
    if not curr.empty and 'direct_cause_category' in curr.columns:
        common_cause = curr['direct_cause_category'].mode()
        cause_label = common_cause.iloc[0] if not common_cause.empty else "N/A"
    else:
        cause_label = "N/A"
    st.markdown(
        '<style>div[data-testid="stMetric"]:last-of-type div[data-testid="stMetricValue"]{font-size:1.1rem;}</style>',
        unsafe_allow_html=True,
    )
    st.metric("Top Cause", cause_label, help=f"Most frequent direct cause category in {current_month_label}.")


def render_site_distribution(charging_sites, selected_categories):
    """Render the site category pie chart."""
    st.subheader("Site Distribution")
    if not selected_categories:
        return

    filtered_sites = charging_sites[charging_sites['site_category'].isin(selected_categories)]
    category_counts = filtered_sites['site_category'].value_counts()

    category_order = ['V2X Chargepoint', 'Building-supplied Charger', 'Other Chargepoint']
    category_colors_pie = {
        'V2X Chargepoint': '#FF1493',
        'Building-supplied Charger': '#0066CC',
        'Other Chargepoint': '#28A745',
    }
    ordered = category_counts.reindex([c for c in category_order if c in category_counts.index])

    fig = px.pie(
        values=ordered.values, names=ordered.index,
        title="Sites by Category", color=ordered.index,
        color_discrete_map=category_colors_pie,
    )
    for trace in fig.data:
        if trace.labels is not None:
            trace.marker.colors = [category_colors_pie.get(lbl, '#888888') for lbl in trace.labels]
    fig.update_layout(height=250, margin=dict(l=100, r=10, t=30, b=0))
    st.plotly_chart(fig)


def render_quick_insights(filtered_outages, charging_sites):
    """Render quick insight boxes."""
    st.subheader("Quick Insights")

    if filtered_outages.empty:
        return

    if 'month_name' in filtered_outages.columns:
        winter_outages = filtered_outages[
            filtered_outages['month_name'].isin(['December', 'January', 'February'])
        ]
        if not winter_outages.empty:
            winter_pct = len(winter_outages) / len(filtered_outages) * 100
            st.markdown(f'<div class="insight-box">{winter_pct:.0f}% of outages occur in winter months</div>', unsafe_allow_html=True)

    if 'duration-hours' in filtered_outages.columns:
        long_outages = filtered_outages[filtered_outages['duration-hours'] > 12]
        if not long_outages.empty:
            long_pct = len(long_outages) / len(filtered_outages) * 100
            st.markdown(f'<div class="insight-box">{long_pct:.0f}% of outages last over 12 hours</div>', unsafe_allow_html=True)

    v2x_sites = len(charging_sites[charging_sites['site_category'] == 'V2X Chargepoint'])
    if v2x_sites > 0:
        st.markdown(f'<div class="insight-box">{v2x_sites} V2X sites can provide grid stability during outages</div>', unsafe_allow_html=True)


def render_ai_recommendations(risk_report):
    """Render AI recommendation cards."""
    st.markdown("---")
    st.subheader("AI Recommendations")

    # Category-specific icons
    category_icons = {
        "Charging Station Placement": "⚡",  # V2X
        "Chargepoint Placement": "🔌",       # Regular chargepoint
        "Grid Resilience": "🏗️",             # Grid infrastructure
        "Community Impact": "🏠",            # Community buildings
    }

    if risk_report and risk_report.recommendations:
        # Show all placement recommendations (V2X and chargepoint)
        placement_categories = ("Charging Station Placement", "Chargepoint Placement")
        charging_recs = [r for r in risk_report.recommendations if r.category in placement_categories]
        other_recs = [r for r in risk_report.recommendations if r.category not in placement_categories]

        # Show charging station recommendations first (these are on the map)
        for rec in charging_recs:
            cat_icon = category_icons.get(rec.category, "📋")
            priority_icon = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(rec.priority, "⚪")
            with st.expander(f"{cat_icon} {priority_icon} {rec.title}", expanded=False):
                st.caption(f"Category: {rec.category} | Priority: {rec.priority}")
                st.markdown(rec.detail)

        # Show other recommendations
        for rec in other_recs[:3]:
            cat_icon = category_icons.get(rec.category, "📋")
            priority_icon = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(rec.priority, "⚪")
            with st.expander(f"{cat_icon} {priority_icon} {rec.title}", expanded=False):
                st.caption(f"Category: {rec.category} | Priority: {rec.priority}")
                st.markdown(rec.detail)
    else:
        st.info("No recommendations generated.")


def render_ai_dashboard(filtered_outages, outages, years, charging_sites, selected_categories, risk_report, risk_predictions):
    """Render the complete right-panel AI Dashboard."""
    st.subheader("AI Dashboard")

    render_metric_cards(filtered_outages, outages, years)
    render_site_distribution(charging_sites, selected_categories)
    render_quick_insights(filtered_outages, charging_sites)
    render_ai_recommendations(risk_report)
