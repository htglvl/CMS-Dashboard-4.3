"""Interactive map creation for the dashboard."""

import numpy as np
import pandas as pd
import folium


def _interpolate_risk(clicked_lat, clicked_lon, risk_predictions, max_radius_km=5.0):
    """Interpolate risk at a clicked point using distance-weighted blending.

    Parameters
    ----------
    clicked_lat : float
        Latitude of clicked point.
    clicked_lon : float
        Longitude of clicked point.
    risk_predictions : pd.DataFrame
        Risk model predictions with lat, lon, prob_high, prob_medium, prob_low.
    max_radius_km : float
        Maximum radius to consider for interpolation.

    Returns
    -------
    dict or None
        Interpolated risk values, or None if no nearby cells found.
    """
    if risk_predictions.empty:
        return None

    # Calculate distances to all grid cells
    lat1 = np.radians(clicked_lat)
    lon1 = np.radians(clicked_lon)
    lat2 = np.radians(risk_predictions["lat"].values)
    lon2 = np.radians(risk_predictions["lon"].values)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    dists = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))

    # Filter cells within radius
    mask = dists <= max_radius_km
    nearby = risk_predictions[mask]
    nearby_dists = dists[mask]

    if len(nearby) == 0:
        return None

    # Distance weights (inverse distance)
    weights = 1.0 / (nearby_dists + 0.001)  # Add small epsilon to avoid division by zero
    weights = weights / weights.sum()

    # Weighted average of probabilities
    prob_high = (nearby["prob_high"].values * weights).sum()
    prob_medium = (nearby["prob_medium"].values * weights).sum()
    prob_low = (nearby["prob_low"].values * weights).sum()

    # Determine risk level
    probs = {"High": prob_high, "Medium": prob_medium, "Low": prob_low}
    risk_level = max(probs, key=probs.get)
    confidence = probs[risk_level]

    return {
        "risk_level": risk_level,
        "confidence": confidence,
        "prob_high": prob_high,
        "prob_medium": prob_medium,
        "prob_low": prob_low
    }


def create_advanced_map(
    charging_sites,
    filtered_outages,
    show_chargepoints: bool = True,
    show_buffers: bool = True,
    show_heatmap: bool = True,
    selected_categories=None,
    live_incidents=None,
    risk_predictions=None,
    show_risk_heatmap: bool = False,
    risk_report=None,
    clicked_lat=None,
    clicked_lng=None,
    clicked_site_name=None,
):
    """
    Create an advanced interactive map with enhanced features.

    Parameters
    ----------
    charging_sites : pd.DataFrame
        DataFrame of charging sites with 'latitude', 'longitude' and
        'site_category'.
    filtered_outages : pd.DataFrame
        DataFrame of outages already filtered by user selections.
    show_buffers : bool, optional
        Whether to display 2-mile buffer circles around each site.
    selected_categories : list of str, optional
        List of site categories to display. If None, all categories are shown.
    live_incidents : pd.DataFrame, optional
        DataFrame of current live incidents.
    risk_predictions : pd.DataFrame, optional
        Risk model predictions with lat, lon, risk_level, confidence.
    show_risk_heatmap : bool, optional
        Whether to display the risk heatmap layer.
    risk_report : InsightReport, optional
        AI recommendation report with charging site suggestions.

    Returns
    -------
    folium.Map
        A Folium map object with markers and optional buffer circles.
    """

    # Center map on charging sites
    center_lat = charging_sites['latitude'].mean()
    center_lon = charging_sites['longitude'].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles=None,
    )
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    if selected_categories is None:
        selected_categories = charging_sites['site_category'].unique()

    # Enhanced color mapping
    category_colors = {
        'V2X Chargepoint': '#FF1493',
        'Building-supplied Charger': '#0066CC',
        'Other Chargepoint': '#28A745'
    }

    # Precompute all site-outage distances in one vectorised pass
    if not filtered_outages.empty:
        out_lat_rad = np.radians(filtered_outages['latitude'].values)
        out_lon_rad = np.radians(filtered_outages['longitude'].values)
        dur_arr = (
            filtered_outages['duration-hours'].values
            if 'duration-hours' in filtered_outages.columns
            else np.zeros(len(filtered_outages))
        )

        # Build datetime array for latest-outage lookup
        if 'Incident Date-time' in filtered_outages.columns:
            dt_arr = filtered_outages['Incident Date-time'].values
        elif 'start_time' in filtered_outages.columns:
            dt_arr = filtered_outages['start_time'].values
        else:
            dt_arr = None

        # Compute distance matrix: (n_sites, n_outages) via broadcasting
        site_lat_rad = np.radians(charging_sites['latitude'].values)
        site_lon_rad = np.radians(charging_sites['longitude'].values)
        dlat = site_lat_rad[:, None] - out_lat_rad[None, :]
        dlon = site_lon_rad[:, None] - out_lon_rad[None, :]
        a = (
            np.sin(dlat / 2) ** 2
            + np.cos(site_lat_rad[:, None])
            * np.cos(out_lat_rad[None, :])
            * np.sin(dlon / 2) ** 2
        )
        dist_km = 6371.0 * 2.0 * np.arcsin(np.sqrt(a))
        dist_mask = dist_km <= 3.218  # within 2-mile buffer

        # Per-site aggregates
        outage_counts = dist_mask.sum(axis=1).astype(float)
        masked_dur = np.where(dist_mask, dur_arr[None, :], 0.0)
        sum_dur = masked_dur.sum(axis=1)
        safe_counts = np.where(outage_counts > 0, outage_counts, 1.0)
        avg_durations = np.where(outage_counts > 0, sum_dur / safe_counts, 0.0)
    else:
        dist_mask = None
        outage_counts = np.zeros(len(charging_sites))
        avg_durations = np.zeros(len(charging_sites))
        dt_arr = None

    if show_chargepoints:
        chargepoint_group = folium.FeatureGroup(name="Chargepoints")
    else:
        chargepoint_group = None

    for site_idx, (idx, site) in enumerate(charging_sites.iterrows()):
        if chargepoint_group is None:
            break
        if site['site_category'] not in selected_categories:
            continue

        outage_count = int(outage_counts[site_idx])
        avg_duration = float(avg_durations[site_idx])

        # Latest outage for this site
        if dist_mask is not None and outage_count > 0 and dt_arr is not None:
            site_dt = dt_arr[dist_mask[site_idx]]
            latest_outage = pd.Series(site_dt).max()
        else:
            latest_outage = "No recent outages"

        popup_html = f"""
        <div style="font-family: Arial; width: 300px; padding: 10px;">
            <h4 style="color: {category_colors.get(site['site_category'], '#000')}; margin-bottom: 10px;">
                {site['charge_point_location']}
            </h4>
            <hr style="margin: 5px 0;">
            <p><strong>Charge point Category:</strong> {site['site_category']}</p>
            <p><strong>Outages in buffer:</strong> {outage_count}</p>
            <p><strong>Average outage duration:</strong> {avg_duration:.1f} hours</p>
            <p><strong>Latest outage:</strong> {str(latest_outage)[:16] if pd.notna(latest_outage) else 'None'}</p>
            <p><strong>Click for detailed analysis</strong></p>
            <hr style="margin: 5px 0;">
            <p style="font-size: 0.8em; color: #666;">
                Coordinates: {site['latitude']:.4f}, {site['longitude']:.4f}
            </p>
        </div>
        """

        marker_size = max(8, min(25, outage_count + 5))

        folium.CircleMarker(
            location=[site['latitude'], site['longitude']],
            radius=marker_size,
            popup=folium.Popup(popup_html, max_width=350),
            color='white',
            fillColor=category_colors.get(site['site_category'], '#000000'),
            fillOpacity=0.8,
            weight=2,
            tooltip=f"{site['charge_point_location']} ({site['site_category']})"
        ).add_to(chargepoint_group)

    if chargepoint_group is not None:
        chargepoint_group.add_to(m)

    # Add search bar using OpenStreetMap Nominatim API
    search_html = """
    <div id="search-container" style="position: absolute; top: 10px; left: 50px; z-index: 1000; width: 300px;">
        <input type="text" id="search-input" placeholder="🔍 Search for a place..."
               style="width: 100%; padding: 8px 12px; border: 2px solid #ccc; border-radius: 4px;
                      font-size: 14px; box-shadow: 0 2px 6px rgba(0,0,0,0.2);">
        <div id="search-results" style="background: white; border: 1px solid #ccc; border-top: none;
                                        border-radius: 0 0 4px 4px; display: none; max-height: 200px;
                                        overflow-y: auto;"></div>
    </div>
    <script>
    var searchMap = null;
    var searchMarker = null;

    function initSearch() {
        var containers = document.querySelectorAll('.folium-map');
        if (containers.length > 0) {
            searchMap = containers[0].__leaflet_map;
        }

        if (!searchMap) {
            setTimeout(initSearch, 500);
            return;
        }

        var input = document.getElementById('search-input');
        var results = document.getElementById('search-results');

        input.addEventListener('keyup', function(e) {
            if (e.key === 'Enter') {
                var query = input.value;
                if (query.length > 2) {
                    fetch('https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(query) + '&limit=5')
                        .then(response => response.json())
                        .then(data => {
                            results.innerHTML = '';
                            if (data.length > 0) {
                                results.style.display = 'block';
                                data.forEach(function(item) {
                                    var div = document.createElement('div');
                                    div.innerHTML = item.display_name;
                                    div.style.padding = '8px 12px';
                                    div.style.cursor = 'pointer';
                                    div.style.borderBottom = '1px solid #eee';
                                    div.addEventListener('click', function() {
                                        searchMap.setView([item.lat, item.lon], 15);
                                        if (searchMarker) {
                                            searchMap.removeLayer(searchMarker);
                                        }
                                        searchMarker = L.marker([item.lat, item.lon])
                                            .addTo(searchMap)
                                            .bindPopup(item.display_name)
                                            .openPopup();
                                        results.style.display = 'none';
                                        input.value = item.display_name;
                                    });
                                    results.appendChild(div);
                                });
                            } else {
                                results.style.display = 'block';
                                results.innerHTML = '<div style="padding: 8px 12px; color: #999;">No results found</div>';
                            }
                        });
                }
            }
        });

        // Hide results when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('#search-container')) {
                results.style.display = 'none';
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSearch);
    } else {
        initSearch();
    }
    </script>
    """

    # Add search bar to map
    m.get_root().html.add_child(folium.Element(search_html))

    # Add outage heatmap
    if show_heatmap and not filtered_outages.empty:
        from folium.plugins import HeatMap

        heat_data = [
            [row['latitude'], row['longitude'], row['duration-hours']]
            for _, row in filtered_outages.iterrows()
            if pd.notna(row['latitude']) and pd.notna(row['longitude'])
        ]

        if heat_data:
            HeatMap(
                heat_data,
                name='Outage Heatmap',
                min_opacity=0.2,
                max_zoom=18,
                radius=15,
                blur=10,
                show=True
            ).add_to(m)

    # ── Risk heatmap layer (smooth) ─────────────────────────────────────
    if show_risk_heatmap and risk_predictions is not None and not risk_predictions.empty:
        from folium.plugins import HeatMap

        # Convert risk levels to numeric weights for smooth heatmap
        risk_weights = {"High": 3.0, "Medium": 2.0, "Low": 1.0}
        heat_data = [
            [row["lat"], row["lon"], risk_weights.get(row["risk_level"], 1.0)]
            for _, row in risk_predictions.iterrows()
        ]

        if heat_data:
            HeatMap(
                heat_data,
                name='Risk Heatmap',
                min_opacity=0.3,
                max_zoom=18,
                radius=20,
                blur=15,
                gradient={0.4: 'green', 0.65: 'yellow', 1: 'red'}
            ).add_to(m)

    # ── AI Recommended Charge Sites ────────────────────────────────────
    if risk_report and hasattr(risk_report, 'recommendations'):
        ai_recs_group = folium.FeatureGroup(name="AI Recommended Sites")

        for rec in risk_report.recommendations:
            if rec.location and rec.category == "Charging Station Placement":
                lat, lon = rec.location

                # Color based on priority
                priority_colors = {
                    "Critical": "#DC3545",
                    "High": "#FD7E14",
                    "Medium": "#FFC107",
                    "Low": "#28A745"
                }
                color = priority_colors.get(rec.priority, "#6C757D")

                popup_html = f"""
                <div style="font-family: Arial; width: 280px; padding: 10px;">
                    <h4 style="color: {color}; margin: 0 0 10px 0;">
                        🤖 {rec.title}
                    </h4>
                    <hr style="margin: 5px 0;">
                    <p style="margin: 5px 0;"><strong>Priority:</strong> {rec.priority}</p>
                    <p style="margin: 5px 0;"><strong>Category:</strong> {rec.category}</p>
                    <p style="margin: 5px 0;"><strong>Score:</strong> {rec.score:.2f}</p>
                    <hr style="margin: 5px 0;">
                    <p style="margin: 5px 0; font-size: 0.9em;">{rec.detail[:200]}...</p>
                    <hr style="margin: 5px 0;">
                    <p style="font-size: 0.8em; color: #666; margin: 5px 0;">
                        📍 {lat:.4f}, {lon:.4f}
                    </p>
                </div>
                """

                # Star marker for AI recommendations
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"🤖 {rec.title}",
                    icon=folium.Icon(
                        color="red" if rec.priority == "Critical" else "orange",
                        icon="star",
                        prefix="fa"
                    )
                ).add_to(ai_recs_group)

        ai_recs_group.add_to(m)

    # ── Live incident markers (red pulsing) ────────────────────────────
    if live_incidents is not None and not live_incidents.empty:
        live_group = folium.FeatureGroup(name="Live Incidents")
        for _, inc in live_incidents.iterrows():
            lat = inc.get("latitude")
            lon = inc.get("longitude")
            if pd.isna(lat) or pd.isna(lon):
                continue

            inc_num = inc.get("incident_num", "N/A")
            status = inc.get("incident_status", "Unknown")
            customers_off = inc.get("customers_off_supply", 0)
            customers_aff = inc.get("customers_affected", 0)
            est_restore = inc.get("estimated_restoration_time")
            restore_str = (
                est_restore.strftime("%d %b %Y, %H:%M")
                if pd.notna(est_restore) else "TBC"
            )

            popup_html = (
                f"<b>🔴 {inc_num}</b><br>"
                f"Status: {status}<br>"
                f"Customers Off Supply: {customers_off:,}/{customers_aff:,}<br>"
                f"Est. Restoration: {restore_str}"
            )
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color="#DC3545",
                fill=True,
                fill_color="#DC3545",
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
            ).add_to(live_group)
        live_group.add_to(m)

    # Add pin marker for clicked location
    if clicked_lat is not None and clicked_lng is not None:
        pin_label = clicked_site_name if clicked_site_name else "📍 Clicked Location"
        folium.Marker(
            location=[clicked_lat, clicked_lng],
            popup=folium.Popup(f"<b>{pin_label}</b><br>📍 {clicked_lat:.4f}, {clicked_lng:.4f}", max_width=250),
            tooltip=pin_label,
            icon=folium.Icon(color="red", icon="map-pin", prefix="fa")
        ).add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    return m
