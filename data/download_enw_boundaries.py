"""Download ENW DfES local authority and county polygon boundaries.

Usage:
    python data/download_enw_boundaries.py
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path

USER_AGENT = "CMS-Dashboard/1.0"
BASE_URL = "https://electricitynorthwest.opendatasoft.com/api/explore/v2.1/catalog/datasets"

DATASETS = {
    "enwl_local_authorities": "enwl_dfes_local_authority_polygons",
    "enwl_counties": "enwl_dfes_county_polygons",
}


def load_api_key() -> str:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return os.environ.get("ENW_API_KEY", "").strip()


def fetch_all_records(dataset_id: str, api_key: str) -> list[dict]:
    all_records = []
    offset = 0
    page_size = 100

    while True:
        params = urllib.parse.urlencode({
            "limit": page_size,
            "offset": offset,
            "apikey": api_key,
        })
        url = f"{BASE_URL}/{dataset_id}/records?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("results", [])
        all_records.extend(results)
        print(f"  {dataset_id}: {len(all_records)}/{data.get('total_count', '?')} records", file=sys.stderr)

        if len(results) < page_size:
            break
        offset += page_size

    return all_records


def records_to_geojson(records: list[dict], name_key: str) -> dict:
    features = []
    for rec in records:
        geo = rec.get("geo_shape")
        if not geo:
            continue

        # geo_shape is a GeoJSON Feature — extract geometry
        geometry = geo.get("geometry", geo)
        props = {k: v for k, v in rec.items() if k not in ("geo_shape", "geo_point_2d")}

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        })

    return {"type": "FeatureCollection", "features": features}


def main():
    api_key = load_api_key()
    if not api_key:
        print("ENW_API_KEY not found.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(__file__).parent

    for name, dataset_id in DATASETS.items():
        print(f"Fetching {dataset_id}...", file=sys.stderr)
        records = fetch_all_records(dataset_id, api_key)

        # Determine the name field
        if "local_authority" in (records[0].keys() if records else []):
            name_key = "local_authority"
        elif "county" in (records[0].keys() if records else []):
            name_key = "county"
        elif "name" in (records[0].keys() if records else []):
            name_key = "name"
        else:
            name_key = None

        geojson = records_to_geojson(records, name_key)
        out_path = output_dir / f"{name}.geojson"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f)

        names = [r.get(name_key, "") for r in records if name_key]
        print(f"  Saved {len(geojson['features'])} features to {out_path.name}")
        print(f"  Names: {sorted(n for n in names if n)[:15]}")

    print("Done.")


if __name__ == "__main__":
    main()
