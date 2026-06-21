"""Tab 5: ML Risk Prediction — predicted risk level and feature importance."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st


@st.cache_resource
def _cached_models():
    from advanced_charts.risk_model import load_models as _load
    return _load()


_fi_cache: dict = {}


def _cached_feature_importance(model, model_name: str):
    from advanced_charts.risk_model import get_feature_importance
    if model_name not in _fi_cache:
        _fi_cache[model_name] = get_feature_importance(model, model_name)
    return _fi_cache[model_name]


def render_risk_prediction(site_outages, site_info, risk_predictions, risk_model_choice):
    """Render ML-predicted risk, probability breakdown, and top features."""
    st.markdown("ML-based Risk Prediction")

    if site_outages.empty:
        st.info("No outage data available for this site.")
        return

    if risk_predictions is None or risk_predictions.empty:
        st.info("Risk predictions not available.")
        return

    site_lat, site_lon = site_info['latitude'], site_info['longitude']

    # Vectorised haversine
    lat1 = np.radians(site_lat)
    lon1 = np.radians(site_lon)
    lat2 = np.radians(risk_predictions['lat'].values)
    lon2 = np.radians(risk_predictions['lon'].values)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    dists = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))

    nearest_idx = dists.argmin()
    nearest_cell = risk_predictions.iloc[nearest_idx]
    dist_km = dists[nearest_idx]

    risk_level = nearest_cell["risk_level"]
    confidence = nearest_cell["confidence"]

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric(
            "Predicted Risk Level", risk_level,
            help=f"Confidence: {confidence:.0%} | Nearest cell: {dist_km:.2f} km away",
        )
    with col_b:
        st.metric("Confidence", f"{confidence:.0%}")

    # Probability breakdown
    st.markdown("**Class Probabilities:**")
    prob_data = {
        "Low": nearest_cell.get("prob_low", 0),
        "Medium": nearest_cell.get("prob_medium", 0),
        "High": nearest_cell.get("prob_high", 0),
    }
    fig_prob = go.Figure(go.Bar(
        x=list(prob_data.keys()),
        y=list(prob_data.values()),
        marker_color=["#28A745", "#FFC107", "#DC3545"],
    ))
    fig_prob.update_layout(
        height=200, margin=dict(l=0, r=0, t=0, b=0),
        yaxis=dict(title="Probability", range=[0, 1]),
    )
    st.plotly_chart(fig_prob, width='stretch')

    # Top features (cached)
    st.markdown("**Top Contributing Features:**")
    try:
        rf_model, xgb_model, xgb_le = _cached_models()
        model = xgb_model if risk_model_choice == "XGBoost" else rf_model
        fi = _cached_feature_importance(model, risk_model_choice)
        for _, row in fi.head(3).iterrows():
            st.markdown(f"• **{row['feature']}** — importance: {row['importance']:.3f}")
    except Exception:
        st.caption("Feature importance not available.")
