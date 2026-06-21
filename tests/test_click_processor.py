"""
Tests for the map click processor.

Scenarios:
1. Nothing → chargepoint
2. Nothing → coordinate
3. Chargepoint → coordinate
4. Chargepoint → chargepoint
5. Coordinate → coordinate
6. Coordinate → chargepoint
7. Click on live incident (not a chargepoint)

st_folium behaviour (from live debug output):
  - Click on empty map:   last_clicked={lat,lng}, last_object_clicked=None
  - Click on marker:      last_clicked=None, last_object_clicked={lat,lng}
                          last_object_clicked_popup=popup HTML
  - Click on live incident: same as marker but popup has incident text, not site name
"""

import pandas as pd
import pytest

from dashboard.click_processor import process_map_click


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def charging_sites():
    """Three chargepoints at known coordinates."""
    return pd.DataFrame([
        {"charge_point_location": "Lancaster University", "latitude": 54.005, "longitude": -2.784, "site_category": "V2X Chargepoint"},
        {"charge_point_location": "Morrisons Lancaster", "latitude": 54.047, "longitude": -2.800, "site_category": "Building-supplied Charger"},
        {"charge_point_location": "Tesco Morecambe", "latitude": 54.070, "longitude": -2.870, "site_category": "Other Chargepoint"},
    ])


# ── Popup HTML strings ───────────────────────────────────────────────────

LANCASTER_POPUP = """
<div style="font-family: Arial; width: 300px; padding: 10px;">
    <h4 style="color: #FF1493;">Lancaster University</h4>
    <p>Charge point Category: V2X Chargepoint</p>
    <p>Outages in buffer: 3</p>
</div>
"""

MORRISONS_POPUP = """
<div style="font-family: Arial; width: 300px; padding: 10px;">
    <h4 style="color: #0066CC;">Morrisons Lancaster</h4>
    <p>Charge point Category: Building-supplied Charger</p>
</div>
"""

TESCO_POPUP = """
<div style="font-family: Arial; width: 300px; padding: 10px;">
    <h4 style="color: #28A745;">Tesco Morecambe</h4>
    <p>Charge point Category: Other Chargepoint</p>
</div>
"""

LIVE_INCIDENT_POPUP = """
🔴 INC 125344704
Status: Dispatched
Customers Off Supply: 4/8
Est. Restoration: 21 Jun 2026, 21:00
"""


def make_map_data(clicked_lat=None, clicked_lng=None,
                  object_lat=None, object_lng=None, popup=None):
    """Build a fake st_folium return dict matching real behaviour."""
    return {
        "last_clicked": {"lat": clicked_lat, "lng": clicked_lng} if clicked_lat is not None else None,
        "last_object_clicked": {"lat": object_lat, "lng": object_lng} if object_lat is not None else None,
        "last_object_clicked_popup": popup,
    }


# ── Tests ─────────────────────────────────────────────────────────────────

class TestNothingToChargepoint:
    """Scenario 1: First click, lands on a chargepoint marker."""

    def test_returns_site_name(self, charging_sites):
        map_data = make_map_data(object_lat=54.005, object_lng=-2.784, popup=LANCASTER_POPUP)
        result = process_map_click(map_data, charging_sites)

        assert result is not None
        assert result["selected_site"] == "Lancaster University"
        assert result["is_chargepoint"] is True

    def test_pin_on_chargepoint_coords(self, charging_sites):
        map_data = make_map_data(object_lat=54.005, object_lng=-2.784, popup=LANCASTER_POPUP)
        result = process_map_click(map_data, charging_sites)

        assert result["pin_lat"] == pytest.approx(54.005)
        assert result["pin_lng"] == pytest.approx(-2.784)


class TestNothingToCoordinate:
    """Scenario 2: First click, lands on empty map (no marker)."""

    def test_returns_coordinates(self, charging_sites):
        map_data = make_map_data(clicked_lat=54.500, clicked_lng=-3.000)
        result = process_map_click(map_data, charging_sites)

        assert result is not None
        assert "Location" in result["selected_site"]
        assert "54.5000" in result["selected_site"]
        assert "-3.0000" in result["selected_site"]
        assert result["is_chargepoint"] is False

    def test_pin_on_clicked_coords(self, charging_sites):
        map_data = make_map_data(clicked_lat=54.500, clicked_lng=-3.000)
        result = process_map_click(map_data, charging_sites)

        assert result["pin_lat"] == pytest.approx(54.500)
        assert result["pin_lng"] == pytest.approx(-3.000)


class TestChargepointToCoordinate:
    """Scenario 3: Previously on a chargepoint, now clicking empty map."""

    def test_switches_to_coordinates(self, charging_sites):
        result1 = process_map_click(
            make_map_data(object_lat=54.005, object_lng=-2.784, popup=LANCASTER_POPUP),
            charging_sites,
        )
        assert result1["is_chargepoint"] is True
        assert result1["selected_site"] == "Lancaster University"

        result2 = process_map_click(
            make_map_data(clicked_lat=54.500, clicked_lng=-3.000),
            charging_sites,
        )
        assert result2["is_chargepoint"] is False
        assert "Location" in result2["selected_site"]
        assert result2["pin_lat"] == pytest.approx(54.500)


class TestChargepointToChargepoint:
    """Scenario 4: Previously on a chargepoint, now clicking a different one."""

    def test_switches_to_new_chargepoint(self, charging_sites):
        result1 = process_map_click(
            make_map_data(object_lat=54.005, object_lng=-2.784, popup=LANCASTER_POPUP),
            charging_sites,
        )
        assert result1["selected_site"] == "Lancaster University"

        result2 = process_map_click(
            make_map_data(object_lat=54.047, object_lng=-2.800, popup=MORRISONS_POPUP),
            charging_sites,
        )
        assert result2["selected_site"] == "Morrisons Lancaster"
        assert result2["is_chargepoint"] is True
        assert result2["pin_lat"] == pytest.approx(54.047)
        assert result2["pin_lng"] == pytest.approx(-2.800)


class TestCoordinateToCoordinate:
    """Scenario 5: Previously on a coordinate, now clicking a different coordinate."""

    def test_switches_to_new_coordinate(self, charging_sites):
        result1 = process_map_click(
            make_map_data(clicked_lat=54.500, clicked_lng=-3.000),
            charging_sites,
        )
        assert result1["is_chargepoint"] is False
        assert result1["pin_lat"] == pytest.approx(54.500)

        result2 = process_map_click(
            make_map_data(clicked_lat=54.200, clicked_lng=-2.500),
            charging_sites,
        )
        assert result2["is_chargepoint"] is False
        assert "54.2000" in result2["selected_site"]
        assert "-2.5000" in result2["selected_site"]
        assert result2["pin_lat"] == pytest.approx(54.200)
        assert result2["pin_lng"] == pytest.approx(-2.500)


class TestCoordinateToChargepoint:
    """Scenario 6: Previously on a coordinate, now clicking a chargepoint."""

    def test_switches_to_chargepoint(self, charging_sites):
        result1 = process_map_click(
            make_map_data(clicked_lat=54.500, clicked_lng=-3.000),
            charging_sites,
        )
        assert result1["is_chargepoint"] is False

        result2 = process_map_click(
            make_map_data(object_lat=54.070, object_lng=-2.870, popup=TESCO_POPUP),
            charging_sites,
        )
        assert result2["selected_site"] == "Tesco Morecambe"
        assert result2["is_chargepoint"] is True
        assert result2["pin_lat"] == pytest.approx(54.070)
        assert result2["pin_lng"] == pytest.approx(-2.870)


class TestLiveIncident:
    """Scenario 7: Click on a live incident marker (not a chargepoint)."""

    def test_live_incident_treated_as_coordinate(self, charging_sites):
        """Live incident popup has no chargepoint site name → coordinate click."""
        map_data = make_map_data(
            object_lat=53.563, object_lng=-2.376,
            popup=LIVE_INCIDENT_POPUP,
        )
        result = process_map_click(map_data, charging_sites)

        assert result["is_chargepoint"] is False
        assert "Location" in result["selected_site"]
        assert result["pin_lat"] == pytest.approx(53.563)
        assert result["pin_lng"] == pytest.approx(-2.376)

    def test_live_incident_does_not_snap_to_nearest_site(self, charging_sites):
        """Should NOT snap to nearest chargepoint when clicking an incident."""
        map_data = make_map_data(
            object_lat=53.563, object_lng=-2.376,
            popup=LIVE_INCIDENT_POPUP,
        )
        result = process_map_click(map_data, charging_sites)

        # Pin should be on the incident, not on any chargepoint
        assert result["pin_lat"] == pytest.approx(53.563)
        assert result["pin_lng"] == pytest.approx(-2.376)
        assert result["selected_site"] != "Lancaster University"
        assert result["selected_site"] != "Morrisons Lancaster"
        assert result["selected_site"] != "Tesco Morecambe"


class TestNoClick:
    """Edge case: no click at all."""

    def test_returns_none(self, charging_sites):
        map_data = {"last_clicked": None, "last_object_clicked": None, "last_object_clicked_popup": None}
        result = process_map_click(map_data, charging_sites)
        assert result is None

    def test_returns_none_when_missing(self, charging_sites):
        map_data = {}
        result = process_map_click(map_data, charging_sites)
        assert result is None
