"""Clean Borderlands community sites data and geocode locations.

Reads the Borderlands Long List Sites Excel file and outputs a cleaned CSV
with geocoded coordinates for use in the Charge My Street suggestions.

Usage:
    python clean_borderlands.py --input "data/Borderlands Long List Sites Apr 26.xlsx" --output data/borderlands_community_sites.csv
"""

import argparse
import logging
import pickle
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Cache file for geocoding results
GEOCACHE_FILE = Path(__file__).parent.parent / "data" / "borderlands_geocache.pkl"

# Site type mapping
SITE_TYPE_MAP = {
    "village hall": "Village Hall",
    "community centre": "Community Centre",
    "community center": "Community Centre",
    "church": "Community Building",
    "chapel": "Community Building",
    "memorial hall": "Community Building",
    "educational institute": "Community Building",
    "parish council": "Community Building",
}


def load_geocache() -> dict:
    """Load geocoding cache from disk."""
    if GEOCACHE_FILE.exists():
        try:
            with open(GEOCACHE_FILE, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            log.warning("Failed to load geocache: %s", e)
    return {}


def save_geocache(cache: dict) -> None:
    """Save geocoding cache to disk."""
    try:
        GEOCACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GEOCACHE_FILE, "wb") as f:
            pickle.dump(cache, f)
    except Exception as e:
        log.warning("Failed to save geocache: %s", e)


def geocode_location(location_name: str, local_authority: str, cache: dict) -> tuple[float, float] | None:
    """Geocode a location using Nominatim with caching.

    Parameters
    ----------
    location_name : str
        Town or village name.
    local_authority : str
        Local authority area (used for disambiguation).
    cache : dict
        Geocoding cache to use/update.

    Returns
    -------
    tuple[float, float] or None
        (latitude, longitude) if successful, None otherwise.
    """
    # Create cache key
    cache_key = f"{location_name}|{local_authority}"

    # Check cache first
    if cache_key in cache:
        return cache[cache_key]

    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(user_agent="cms_dashboard", timeout=10)

        # Try with full location string
        query = f"{location_name}, {local_authority}, UK"
        location = geolocator.geocode(query)

        if location:
            result = (location.latitude, location.longitude)
            cache[cache_key] = result
            log.info("Geocoded '%s' to (%.4f, %.4f)", location_name, result[0], result[1])
            return result

        # Try without local authority
        query = f"{location_name}, UK"
        location = geolocator.geocode(query)

        if location:
            result = (location.latitude, location.longitude)
            cache[cache_key] = result
            log.info("Geocoded '%s' to (%.4f, %.4f)", location_name, result[0], result[1])
            return result

        log.warning("Could not geocode '%s'", location_name)
        cache[cache_key] = None
        return None

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        log.warning("Geocoding error for '%s': %s", location_name, e)
        return None
    except Exception as e:
        log.warning("Unexpected error geocoding '%s': %s", location_name, e)
        return None


def classify_site_type(potential_sites: str, brief_description: str) -> str:
    """Classify site type based on Potential Sites and Brief Description.

    Parameters
    ----------
    potential_sites : str
        The Potential Sites field from the Excel file.
    brief_description : str
        The Brief Description field from the Excel file.

    Returns
    -------
    str
        Classified site type.
    """
    # Combine fields for matching
    text = f"{potential_sites} {brief_description}".lower()

    # Check for matches in priority order
    for key, site_type in SITE_TYPE_MAP.items():
        if key in text:
            return site_type

    # Default
    return "Other Community Site"


def clean_borderlands(input_path: str, output_path: str) -> dict:
    """Clean Borderlands data and geocode locations.

    Parameters
    ----------
    input_path : str
        Path to the Borderlands Excel file.
    output_path : str
        Path where the cleaned CSV will be saved.

    Returns
    -------
    dict
        Keys: success (bool), error (str or None), output_path (str),
        geocoded_count (int), total_count (int).
    """
    try:
        # Read Excel file (header=1 to skip the title row)
        df = pd.read_excel(input_path, engine="openpyxl", header=1)
    except Exception as e:
        return {"success": False, "error": f"Failed to read Excel file: {e}",
                "output_path": output_path, "geocoded_count": 0, "total_count": 0}

    # Normalize column names
    df.columns = df.columns.str.strip()

    # Expected columns
    required_cols = ["Town/ Village", "Potential Sites", "Brief Description", "Local Authority Area"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return {"success": False, "error": f"Missing required columns: {missing}",
                "output_path": output_path, "geocoded_count": 0, "total_count": len(df)}

    # Load geocache
    cache = load_geocache()

    # Process each row
    results = []
    geocoded_count = 0
    total_count = len(df)

    for idx, row in df.iterrows():
        town = str(row["Town/ Village"]).strip()
        potential_sites = str(row["Potential Sites"]).strip()
        brief_desc = str(row["Brief Description"]).strip()
        local_authority = str(row["Local Authority Area"]).strip()

        # Skip empty rows
        if town == "nan" or potential_sites == "nan":
            continue

        # Classify site type
        site_type = classify_site_type(potential_sites, brief_desc)

        # Create site name
        site_name = f"{town} - {potential_sites}"

        # Geocode
        coords = geocode_location(town, local_authority, cache)

        if coords:
            lat, lon = coords
            geocoded_count += 1
        else:
            lat, lon = None, None

        results.append({
            "site_name": site_name,
            "site_type": site_type,
            "latitude": lat,
            "longitude": lon,
            "local_authority": local_authority,
            "brief_description": brief_desc,
        })

        # Rate limiting for Nominatim (1 request per second)
        time.sleep(1.1)

    # Save geocache
    save_geocache(cache)

    # Create output DataFrame
    output_df = pd.DataFrame(results)

    # Remove rows without coordinates
    output_df = output_df.dropna(subset=["latitude", "longitude"])

    # Save to CSV
    output_df.to_csv(output_path, index=False, encoding="utf-8")

    log.info("Saved %d geocoded sites to %s", len(output_df), output_path)

    return {
        "success": True,
        "error": None,
        "output_path": output_path,
        "geocoded_count": geocoded_count,
        "total_count": total_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Clean Borderlands community sites data.")
    parser.add_argument("--input", required=True, help="Path to the Borderlands Excel file")
    parser.add_argument("--output", default="data/borderlands_community_sites.csv",
                        help="Path to save the cleaned CSV")
    args = parser.parse_args()

    result = clean_borderlands(args.input, args.output)

    if result["success"]:
        print(f"✓ Successfully cleaned Borderlands data")
        print(f"  Geocoded: {result['geocoded_count']}/{result['total_count']} sites")
        print(f"  Output: {result['output_path']}")
    else:
        print(f"✗ Error: {result['error']}")
        exit(1)


if __name__ == "__main__":
    main()
