"""Interactive map creation for the dashboard."""

import hashlib
import numpy as np
import pandas as pd
import folium

# Module-level cache for heatmap data
_heatmap_cache_key = None
_heatmap_cache_data = None


def _build_heatmap_data(filtered_outages):
    """Build heatmap data from filtered outages, with caching.

    Returns a list of [lat, lng, weight] triples.
    Cached — only recomputes when the filtered data changes.
    """
    global _heatmap_cache_key, _heatmap_cache_data

    if filtered_outages.empty:
        return []

    try:
        _key = hashlib.md5(
            pd.util.hash_pandas_object(filtered_outages).values.tobytes()
        ).hexdigest()
    except Exception:
        _key = f"{len(filtered_outages)}_{filtered_outages['latitude'].sum():.6f}"

    if _key == _heatmap_cache_key and _heatmap_cache_data is not None:
        return _heatmap_cache_data

    _valid = filtered_outages['latitude'].notna() & filtered_outages['longitude'].notna()
    _lats = filtered_outages.loc[_valid, 'latitude'].values
    _lngs = filtered_outages.loc[_valid, 'longitude'].values
    _durs = (
        filtered_outages.loc[_valid, 'duration-hours'].values
        if 'duration-hours' in filtered_outages.columns
        else np.ones(_valid.sum())
    )

    _heat = np.column_stack([_lats, _lngs, _durs]).tolist()

    _heatmap_cache_key = _key
    _heatmap_cache_data = _heat

    return _heat


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
    show_layers=None,
    selected_categories=None,
    live_incidents=None,
    risk_predictions=None,
    confidence_threshold: float = 0.5,
    risk_report=None,
    clicked_lat=None,
    clicked_lng=None,
    clicked_site_name=None,
    flexibility_tenders=None,
    monthly_tenders=None,
    enw_counties=None,
    enw_local_authorities=None,
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
    show_layers : list of str, optional
        Layer names to display. If None, all layers are shown.
    selected_categories : list of str, optional
        List of site categories to display. If None, all categories are shown.
    live_incidents : pd.DataFrame, optional
        DataFrame of current live incidents.
    risk_predictions : pd.DataFrame, optional
        Risk model predictions with lat, lon, risk_level, confidence.
    confidence_threshold : float, optional
        Minimum model confidence for risk heatmap cells.
    risk_report : InsightReport, optional
        AI recommendation report with charging site suggestions.
    flexibility_tenders : GeoDataFrame, optional
        Dissolved GeoDataFrame of flexibility tender polygons (one per substation).

    Returns
    -------
    folium.Map
        A Folium map object with markers and optional buffer circles.
    """

    if show_layers is None:
        show_layers = [
            "Chargepoints", "Buffer Zones", "Outage Heatmap",
            "Risk Heatmap", "Flexibility Tenders", "AI Recommended Sites",
            "Live Incidents",
        ]

    # Center map on charging sites
    center_lat = charging_sites['latitude'].mean()
    center_lon = charging_sites['longitude'].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles=None,
    )
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

    # ── ENW boundary overlays (rendered first = bottom layer) ─────────
    if "ENW Counties" in show_layers and enw_counties is not None and not enw_counties.empty:
        counties_group = folium.FeatureGroup(name="ENW Counties")
        for _, row in enw_counties.iterrows():
            name = row.get("county", row.get("name", "Unknown"))
            geo_json = folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda x: {
                    "fillColor": "transparent",
                    "color": "#888888",
                    "weight": 1.5,
                    "fillOpacity": 0,
                },
                highlight_function=lambda x: {
                    "weight": 3,
                    "color": "#333333",
                },
                tooltip=folium.Tooltip(f"<b>{name}</b>"),
            )
            geo_json.add_to(counties_group)
        counties_group.add_to(m)

    if "ENW Local Authorities" in show_layers and enw_local_authorities is not None and not enw_local_authorities.empty:
        la_group = folium.FeatureGroup(name="ENW Local Authorities")
        for _, row in enw_local_authorities.iterrows():
            name = row.get("local_authority", row.get("name", "Unknown"))
            geo_json = folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda x: {
                    "fillColor": "transparent",
                    "color": "#5B9BD5",
                    "weight": 1,
                    "fillOpacity": 0,
                },
                highlight_function=lambda x: {
                    "weight": 2.5,
                    "color": "#2E75B6",
                },
                tooltip=folium.Tooltip(f"<b>{name}</b>"),
            )
            geo_json.add_to(la_group)
        la_group.add_to(m)

    if selected_categories is None:
        selected_categories = charging_sites['site_category'].unique()

    # Enhanced color mapping
    category_colors = {
        'V2X Chargepoint': '#FF1493',
        'Building-supplied Charger': '#0066CC',
        'Other Chargepoint': '#28A745'
    }

    # ── Per-site outage stats via KD-tree (no full distance matrix) ────
    _BUFFER_KM = 3.218  # 2 miles

    # Per-site arrays: count, avg duration, latest outage
    outage_counts = np.zeros(len(charging_sites))
    avg_durations = np.zeros(len(charging_sites))
    latest_outages = [None] * len(charging_sites)

    if not filtered_outages.empty:
        from scipy.spatial import cKDTree

        valid_mask = filtered_outages['latitude'].notna() & filtered_outages['longitude'].notna()
        out_lats = filtered_outages.loc[valid_mask, 'latitude'].values
        out_lons = filtered_outages.loc[valid_mask, 'longitude'].values
        dur_arr = (
            filtered_outages.loc[valid_mask, 'duration-hours'].values
            if 'duration-hours' in filtered_outages.columns
            else np.zeros(valid_mask.sum())
        )

        # Datetime array for latest-outage lookup
        if 'Incident Date-time' in filtered_outages.columns:
            dt_arr = filtered_outages.loc[valid_mask, 'Incident Date-time'].values
        elif 'start_time' in filtered_outages.columns:
            dt_arr = filtered_outages.loc[valid_mask, 'start_time'].values
        else:
            dt_arr = None

        # Convert outage coords to radians for KD-tree (haversine needs radians)
        out_pts = np.column_stack([np.radians(out_lats), np.radians(out_lons)])
        tree = cKDTree(out_pts)

        # Convert site coords to radians
        site_lats_rad = np.radians(charging_sites['latitude'].values)
        site_lons_rad = np.radians(charging_sites['longitude'].values)

        # Angular radius corresponding to 2 miles on Earth
        _ANGULAR_RADIUS = _BUFFER_KM / 6371.0

        for i in range(len(charging_sites)):
            # Query tree for all outages within angular radius
            idxs = tree.query_ball_point([site_lats_rad[i], site_lons_rad[i]], _ANGULAR_RADIUS)
            if not idxs:
                continue
            outage_counts[i] = len(idxs)
            avg_durations[i] = dur_arr[idxs].mean()
            if dt_arr is not None:
                latest_outages[i] = pd.Series(dt_arr[idxs]).max()
    else:
        dt_arr = None

    # ── Risk heatmap layer (rendered below chargepoints) ─────────────
    if "Risk Heatmap" in show_layers and risk_predictions is not None and not risk_predictions.empty:
        risk_group = folium.FeatureGroup(name='Risk Heatmap')

        cell_size = 0.01  # half of 0.02° grid cell

        # Gradient color function: green → yellow → red based on risk score
        def _risk_color(prob_high, prob_medium):
            # Blend: green (low) → yellow (medium) → red (high)
            r = int(min(255, (prob_high * 255 + prob_medium * 200)))
            g = int(min(255, ((1 - prob_high) * 200 + prob_medium * 100)))
            b = int(max(0, (1 - prob_high - prob_medium) * 150))
            return f"#{r:02x}{g:02x}{b:02x}"

        for _, row in risk_predictions.iterrows():
            lat, lon = row["lat"], row["lon"]
            level = row.get("risk_level", "Low")
            confidence = row.get("confidence", 0)

            # Skip low risk cells and low confidence
            if level == "Low" or confidence < confidence_threshold:
                continue

            prob_h = row.get("prob_high", 0)
            prob_m = row.get("prob_medium", 0)

            color = _risk_color(prob_h, prob_m)
            # Higher risk = more opaque
            opacity = 0.4 + (prob_h * 0.4) + (prob_m * 0.15)

            rect = folium.Rectangle(
                bounds=[[lat - cell_size, lon - cell_size],
                        [lat + cell_size, lon + cell_size]],
                color=None,
                fill=True,
                fill_color=color,
                fill_opacity=min(opacity, 0.8),
                weight=0,
                interactive=False,
                class_name="risk-cell",
            )
            rect.add_to(risk_group)

        risk_group.add_to(m)

        # Inject JS to make risk heatmap SVG elements clickthrough
        risk_js = """
        <script>
        (function() {
            function makeRiskClickthrough() {
                var paths = document.querySelectorAll('.risk-cell');
                paths.forEach(function(p) {
                    p.style.pointerEvents = 'none';
                });
            }
            setTimeout(makeRiskClickthrough, 500);
        })();
        </script>
        """
        m.get_root().html.add_child(folium.Element(risk_js))

    # ── Biannual Tender polygons ───────────────────────────────────────
    if "Biannual Tenders" in show_layers and flexibility_tenders is not None and not flexibility_tenders.empty:
        flex_group = folium.FeatureGroup(name="Biannual Tenders")

        _flex_colors = {
            "Variable Availability": ("#0066CC", "#004C99"),
            "Variable Availability + Operational Utilisation": ("#7B2D8E", "#5A1F68"),
        }
        _flex_default = ("#6C757D", "#4E555B")

        for _, row in flexibility_tenders.iterrows():
            need = str(row.get("need_type", ""))
            fill_color, border_color = _flex_colors.get(need, _flex_default)
            substation = row.get("substation_name", "Unknown")

            tooltip_html = f"<b>{substation}</b><br>{need}"

            geo_json = folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda x, fc=fill_color, bc=border_color: {
                    "fillColor": fc,
                    "color": bc,
                    "weight": 1,
                    "fillOpacity": 0.3,
                },
                highlight_function=lambda x: {
                    "fillOpacity": 0.6,
                    "weight": 2,
                },
                tooltip=folium.Tooltip(tooltip_html),
            )
            geo_json.add_child(folium.Popup(
                f'<div class="flex-tender" data-substation="{substation}"><b>{substation}</b></div>',
                max_width=200,
            ))
            geo_json.add_to(flex_group)

        flex_group.add_to(m)

    # ── Monthly Tender polygons ────────────────────────────────────────
    if "Monthly Tenders" in show_layers and monthly_tenders is not None and not monthly_tenders.empty:
        monthly_group = folium.FeatureGroup(name="Monthly Tenders")

        _monthly_colors = {
            "Variable Availability": ("#E67E22", "#D35400"),
            "Variable Availability + Operational Utilisation": ("#8E44AD", "#6C3483"),
        }
        _monthly_default = ("#95A5A6", "#7F8C8D")

        for _, row in monthly_tenders.iterrows():
            need = str(row.get("need_type", ""))
            fill_color, border_color = _monthly_colors.get(need, _monthly_default)
            substation = row.get("substation_name", "Unknown")

            tooltip_html = f"<b>{substation}</b><br>{need}"

            geo_json = folium.GeoJson(
                data=row["geometry"].__geo_interface__,
                style_function=lambda x, fc=fill_color, bc=border_color: {
                    "fillColor": fc,
                    "color": bc,
                    "weight": 1,
                    "fillOpacity": 0.3,
                },
                highlight_function=lambda x: {
                    "fillOpacity": 0.6,
                    "weight": 2,
                },
                tooltip=folium.Tooltip(tooltip_html),
            )
            geo_json.add_child(folium.Popup(
                f'<div class="flex-tender" data-substation="{substation}"><b>{substation}</b></div>',
                max_width=200,
            ))
            geo_json.add_to(monthly_group)

        monthly_group.add_to(m)

    buffer_group = folium.FeatureGroup(name="Buffer Zones") if "Buffer Zones" in show_layers else None
    chargepoint_group = folium.FeatureGroup(name="Chargepoints") if "Chargepoints" in show_layers else None

    for site_idx, (idx, site) in enumerate(charging_sites.iterrows()):
        if chargepoint_group is None:
            break
        if site['site_category'] not in selected_categories:
            continue

        outage_count = int(outage_counts[site_idx])
        avg_duration = float(avg_durations[site_idx])

        # Latest outage for this site
        latest_outage = latest_outages[site_idx] if latest_outages[site_idx] is not None else "No recent outages"

        popup_html = f"""
        <div style="font-family: Arial; width: 300px; padding: 10px;">
            <h4 style="color: {category_colors.get(site['site_category'], '#000')}; margin-bottom: 10px;">
                {site['charge_point_location']}
            </h4>
            <p><strong>Charge point Category:</strong> {site['site_category']}</p>
            <p><strong>Outages in buffer:</strong> {outage_count}</p>
            <p><strong>Average outage duration:</strong> {avg_duration:.1f} hours</p>
            <p><strong>Latest outage:</strong> {str(latest_outage)[:16] if pd.notna(latest_outage) else 'None'}</p>
            <p style="font-size: 0.8em; color: #666;">
                Coordinates: {site['latitude']:.4f}, {site['longitude']:.4f}
            </p>
        </div>
        """

        marker_size = max(8, min(15, outage_count + 5))

        # Add 2-mile buffer FIRST (below markers)
        if buffer_group is not None:
            folium.Circle(
                location=[site['latitude'], site['longitude']],
                radius=3218,  # 2 miles in meters
                color=category_colors.get(site['site_category'], '#000000'),
                fill=True,
                fillColor=category_colors.get(site['site_category'], '#000000'),
                fillOpacity=0.08,
                weight=1,
                dash_array='5, 5',
                interactive=False,  # Click-through
            ).add_to(buffer_group)

        # Add chargepoint marker SECOND (above buffer)
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

    # Add buffer group first (below), then chargepoint group (above)
    if buffer_group is not None:
        buffer_group.add_to(m)
    if chargepoint_group is not None:
        chargepoint_group.add_to(m)

    # Add outage heatmap (cached, vectorized)
    if "Outage Heatmap" in show_layers and not filtered_outages.empty:
        from folium.plugins import HeatMap

        _heat = _build_heatmap_data(filtered_outages)

        if _heat:
            HeatMap(
                _heat,
                name='Outage Heatmap',
                min_opacity=0.2,
                max_zoom=18,
                radius=15,
                blur=10,
                show=True
            ).add_to(m)

    # ── AI Recommended Charge Sites ────────────────────────────────────
    if "AI Recommended Sites" in show_layers and risk_report and hasattr(risk_report, 'recommendations'):
        ai_recs_group = folium.FeatureGroup(name="AI Recommended Sites")

        for rec in risk_report.recommendations:
            if rec.location and rec.category in ("Charging Station Placement", "Chargepoint Placement"):
                lat, lon = rec.location

                # Color and icon based on category
                is_v2x = rec.category == "Charging Station Placement"
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
                        {rec.title}
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

                # Bolt for V2X, plug for chargepoint
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=300),
                    tooltip=f"{rec.title}",
                    icon=folium.Icon(
                        color="red" if is_v2x else "blue",
                        icon="bolt" if is_v2x else "plug",
                        prefix="fa"
                    )
                ).add_to(ai_recs_group)

        ai_recs_group.add_to(m)

    # ── Live incident markers (red pulsing) ────────────────────────────
    if "Live Incidents" in show_layers and live_incidents is not None and not live_incidents.empty:
        live_group = folium.FeatureGroup(name="Live Incidents")
        for _, inc in live_incidents.iterrows():
            lat = inc.get("latitude")
            lon = inc.get("longitude")
            if pd.isna(lat) or pd.isna(lon):
                continue

            inc_num = inc.get("incident_num", "N/A")
            status = inc.get("incident_status", "Unknown")
            customers_off = int(inc.get("customers_off_supply", 0) or 0)
            customers_aff = int(inc.get("customers_affected", 0) or 0)
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
            # Build tooltip: "INC 12345 — High Voltage Fault"
            cause = inc.get("incident_type", "")
            tooltip_text = f"{inc_num} - {cause}" if cause else f"{inc_num}"

            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color="#DC3545",
                fill=True,
                fill_color="#DC3545",
                fill_opacity=0.8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=tooltip_text,
            ).add_to(live_group)
        live_group.add_to(m)

    # Add pin marker and 2-mile buffer for clicked location (clickthrough)
    if clicked_lat is not None and clicked_lng is not None:
        pin_label = clicked_site_name if clicked_site_name else "📍 Clicked Location"

        # Add 2-mile buffer around pin
        folium.Circle(
            location=[clicked_lat, clicked_lng],
            radius=3218,  # 2 miles in meters
            color="#FF1493",
            fill=True,
            fillColor="#FF1493",
            fillOpacity=0.1,
            weight=2,
            dash_array='5, 5',
            interactive=False,
        ).add_to(m)

        # Add pin marker using DivIcon so it's clickthrough
        folium.Marker(
            location=[clicked_lat, clicked_lng],
            icon=folium.DivIcon(
                html=f'<div style="font-size:24px;pointer-events:none;">📍</div>',
                icon_size=(30, 30),
                icon_anchor=(15, 30),
            ),
        ).add_to(m)

    # Add layer control
    folium.LayerControl().add_to(m)

    return m
