"""
Click processing logic for the CMS Dashboard map.

Handles detection of chargepoint vs coordinate clicks using
st_folium's last_object_clicked and last_object_clicked_popup
(not threshold-based).

st_folium behaviour:
  - Click on empty map: last_clicked={lat,lng}, last_object_clicked=None
  - Click on marker:    last_clicked=None, last_object_clicked={lat,lng}
                        last_object_clicked_popup=popup HTML
"""

import numpy as np


def _find_site_from_popup(popup_html, charging_sites):
    """Match a popup HTML to a chargepoint by checking if the site name
    appears in the popup content."""
    if not popup_html:
        return None
    for _, site in charging_sites.iterrows():
        if site['charge_point_location'] in popup_html:
            return site
    return None


def process_map_click(map_data, charging_sites):
    """Process a map click and determine the selected site and pin location.

    Parameters
    ----------
    map_data : dict
        Return value from st_folium(), contains 'last_clicked',
        'last_object_clicked', and 'last_object_clicked_popup'.
    charging_sites : pd.DataFrame
        DataFrame with 'latitude', 'longitude', 'charge_point_location' columns.

    Returns
    -------
    dict or None
        If click should be processed, returns:
        {
            'pin_lat': float,
            'pin_lng': float,
            'selected_site': str,
            'is_chargepoint': bool,
        }
        If no new click, returns None.
    """
    has_click = map_data.get('last_clicked') is not None
    has_object = map_data.get('last_object_clicked') is not None

    # No click at all
    if not has_click and not has_object:
        return None

    # Click on a marker — last_object_clicked has coords, last_clicked is None
    if has_object:
        object_clicked = map_data['last_object_clicked']
        obj_lat = object_clicked.get('lat')
        obj_lng = object_clicked.get('lng')

        # Check if popup contains an actual chargepoint site name
        # (not a live incident or other non-chargepoint marker)
        popup_html = map_data.get('last_object_clicked_popup')
        matched_site = _find_site_from_popup(popup_html, charging_sites)

        if matched_site is not None:
            return {
                'pin_lat': float(matched_site['latitude']),
                'pin_lng': float(matched_site['longitude']),
                'selected_site': matched_site['charge_point_location'],
                'is_chargepoint': True,
            }

        # Object clicked but not a chargepoint (e.g. live incident)
        # Treat as coordinate click
        return {
            'pin_lat': obj_lat,
            'pin_lng': obj_lng,
            'selected_site': f"\U0001f4cd Location ({obj_lat:.4f}, {obj_lng:.4f})",
            'is_chargepoint': False,
        }

    # Click on empty map — last_clicked has coords, last_object_clicked is None
    clicked_lat = map_data['last_clicked']['lat']
    clicked_lng = map_data['last_clicked']['lng']

    return {
        'pin_lat': clicked_lat,
        'pin_lng': clicked_lng,
        'selected_site': f"\U0001f4cd Location ({clicked_lat:.4f}, {clicked_lng:.4f})",
        'is_chargepoint': False,
    }
