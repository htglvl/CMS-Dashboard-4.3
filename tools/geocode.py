"""Convert place name to lat/long using Nominatim (OpenStreetMap).

Usage:
    python tools/geocode.py --query "Lancaster"
    python tools/geocode.py --query "LA1 1YW"
    python tools/geocode.py --query "Kendal" --limit 5
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import urllib.request
import urllib.parse


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CMS-Dashboard/1.0"


def geocode(query: str, limit: int = 3) -> list[dict]:
    """Geocode a place name using Nominatim."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": limit,
        "addressdetails": 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    results = []
    for item in data:
        address = item.get("address", {})
        # Extract meaningful name
        name = (address.get("village") or
                address.get("town") or
                address.get("city") or
                address.get("suburb") or
                address.get("hamlet") or
                item.get("display_name", "").split(",")[0])

        results.append({
            "name": name.strip() if name else query,
            "lat": round(float(item["lat"]), 6),
            "lon": round(float(item["lon"]), 6),
            "type": item.get("type", ""),
            "display_name": item.get("display_name", ""),
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Convert place name to lat/long coordinates.")
    parser.add_argument("--query", type=str, required=True, help="Place name, address, or postcode")
    parser.add_argument("--limit", type=int, default=3, help="Max number of results")
    args = parser.parse_args()

    try:
        results = geocode(args.query, args.limit)
        output = {
            "query": args.query,
            "count": len(results),
            "results": results,
        }
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
