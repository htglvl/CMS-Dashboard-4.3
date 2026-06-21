"""
Utility script for cleaning raw Charge My Street charging site exports.

Transforms raw CSV files into the canonical format used by the CMS dashboard:

* ``all_charging_sites.csv`` — columns:
  ``charge_point_location``, ``site_category``, ``latitude``, ``longitude``.

Unplanned outage data is fetched and cleaned automatically by
``fetch_outages.py`` via the ENW API — no manual cleaning needed.

Usage (command-line):

```bash
python clean_datasets.py --input path/to/raw.csv --output dataset/all_charging_sites.csv
```

Alternatively, import the ``clean_chargepoints`` function into your own scripts.
"""

import argparse
import pandas as pd


def clean_chargepoints(input_path: str, output_path: str) -> None:
    """Clean a raw chargepoints dataset and save it in the dashboard format.

    The function extracts the key fields required by the CMS dashboard: a
    human-readable location name, a site category, and geographic
    coordinates. It recognises common field names for these attributes and
    ignores other columns to avoid accidental renaming. The cleaned
    dataset contains the columns `charge_point_location`,
    `site_category`, `latitude` and `longitude`.

    Parameters
    ----------
    input_path : str
        Path to the raw CSV file containing chargepoint information.
    output_path : str
        Path where the cleaned CSV will be saved.
    """
    import csv
    # Robustly read the raw export.  Some Charge My Street exports wrap
    # every field in double quotes and include embedded commas; other
    # exports include a mixture of quoted and unquoted fields.  Using
    # the Python CSV engine with an explicit `quotechar` and
    # `escapechar` ensures that quoted commas are treated as part of
    # the field rather than as delimiters.  If this parse fails for
    # some reason, fall back to the default parser with minimal
    # quoting.
    try:
        df = pd.read_csv(
            input_path,
            engine="python",
            quotechar='"',
            escapechar='\\',
            on_bad_lines='skip'
        )
    except Exception:
        # Fallback to a more permissive parser.  We deliberately avoid
        # QUOTE_NONE here because it can incorrectly split fields
        # containing commas when the export encloses values in quotes.
        df = pd.read_csv(input_path, encoding='utf-8', on_bad_lines='skip')
    # Remove any surrounding quotes from column names and trim whitespace
    df.columns = df.columns.astype(str).str.strip().str.strip('"')
    # Build a mapping from raw column names to the expected names.  In addition
    # to location, latitude, longitude and vx flag, we need to capture the
    # chargepoint status (e.g. open, cwys) so we can filter inactive or
    # potential sites.  We map the common status field names to a unified
    # `cp_status` column.
    rename_map: dict[str, str] = {}
    for col in df.columns:
        col_clean = col.lower().strip()
        # Location / site name
        if col_clean in {
            'field_place_name|value', 'place_name', 'field_site_name|value',
            'location', 'charge_point_location', 'site_name'
        }:
            rename_map[col] = 'charge_point_location'
        # Latitude
        elif col_clean in {'field_latitude|value', 'latitude', 'lat', 'lat_val'}:
            rename_map[col] = 'latitude'
        # Longitude
        elif col_clean in {'field_longitude|value', 'longitude', 'lon', 'lng', 'long'}:
            rename_map[col] = 'longitude'
        # V2X flag
        elif col_clean in {'field_vx_bool|value', 'vx', 'v2x', 'vx_flag'}:
            rename_map[col] = 'vx_flag'
        # Explicit site category columns
        elif col_clean in {'category', 'site_category'}:
            rename_map[col] = 'site_category'
        # Status of the chargepoint (open, cwys, etc.)
        elif col_clean in {'field_cp_status|value', 'cp_status', 'status', 'field_cp_status'}:
            rename_map[col] = 'cp_status'
        # Do not rename other columns to avoid duplicates

    df = df.rename(columns=rename_map)
    # Strip extraneous quotes and whitespace from key fields.  Convert
    # the vx flag to numeric (treat the string "Array" and empty
    # strings as missing and fill with 0).  Removing quotes from
    # latitude/longitude allows numeric conversion later on.
    for col in ['charge_point_location', 'latitude', 'longitude', 'vx_flag']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.strip('"')
    if 'vx_flag' in df.columns:
        # Convert to numeric; replace non‑numeric placeholders with NaN then fill with 0
        df['vx_flag'] = df['vx_flag'].replace({'Array': None, '': None}).astype(float, errors='ignore')
        df['vx_flag'] = pd.to_numeric(df['vx_flag'], errors='coerce').fillna(0).astype(int)
    # Prepare chargepoint status.  If cp_status exists, normalise by
    # stripping whitespace and converting to lowercase; otherwise set to
    # unknown.  Some datasets may not include cp_status; in that case,
    # assume unknown and include all sites.
    if 'cp_status' in df.columns:
        # Normalise the status by stripping whitespace and surrounding quotes,
        # then lowercasing.  Many raw exports wrap values in double quotes.
        df['cp_status'] = (
            df['cp_status']
            .astype(str)
            .str.strip()
            .str.strip('"')
            .str.lower()
        )
    else:
        df['cp_status'] = 'unknown'

    # Define a list of locations that correspond to building‑supplied
    # chargers.  These names are taken from the original notebook used to
    # clean the data.  If a site's name appears in this list, it will be
    # classified as a Building‑supplied Charger regardless of its status.
    # A curated list of locations where the charging hardware is powered
    # directly by the host building rather than the grid.  This list is
    # derived from the original Jupyter notebooks used to prepare the
    # CMS dashboard.  Duplicate entries (e.g. "Arnside Educational
    # Institute" appeared twice) have been removed.  When a site's
    # name matches one of these entries, it will be categorised as a
    # "Building‑supplied Charger" unless it also qualifies as a V2X
    # Chargepoint (which takes priority).
    building_sites_list = [
        "Rydal Hall",
        "Keswick Quaker Meeting House",
        "Alresford Parish Council Car Park",
        "Bampton Memorial Hall",
        "Eaglesfield Village Hall",
        "Skelton Toppin Memorial Hall",
        "Gamblesby Community Centre",
        "Adams Recreation Ground",
        "Arnside Educational Institute",
        "Cedar Road Car Park, Marsh, Lancaster",
        "Alston Community Gym, Tyne Willows",
        "Yealands Village Hall",
        "Stanhope Masonic Hall",
        "Weardale Community Transport",
        "Hamsterley Colliery",
        "Newbiggin Village Hall",
        "Haven Cottage B&B",
    ]
    # Normalise building site names for comparison: strip extra spaces,
    # convert to lowercase and remove newline characters.
    building_sites_set = set(name.strip().lower() for name in building_sites_list)

    # Derive the site category using the V2X flag, status and building site list.
    def classify_site(row) -> str | None:
        """Assign a site category based on V2X flag, status and known building sites.

        This logic follows the original Jupyter notebooks used to prepare the
        chargepoint datasets.  It works as follows:

        * If the site has a V2X flag of 1 (truthy) and its status is either
          ``open`` or ``cwys`` (construction works), classify it as a V2X
          chargepoint.  These two statuses indicate an operational or nearly
          operational site.  **This takes priority over any building-site
          designation**, so a V2X site in the building list will still be
          classified as "V2X Chargepoint".
        * Otherwise, if the site name is in the ``building_sites_list``, classify
          it as ``"Building-supplied Charger"`` regardless of its status.
        * Otherwise, if the site is not V2X and has status exactly ``open``, classify
          it as an "Other Chargepoint".  Sites marked as ``cwys`` but not
          V2X are considered future/potential sites and are excluded.
        * Any other combination (e.g. comingsoon, check, hibernate, unknown)
          will be filtered out by returning ``None``.

        Parameters
        ----------
        row : pandas.Series
            A row of the raw chargepoints DataFrame.

        Returns
        -------
        str or None
            The assigned site category, or ``None`` if the row should be
            excluded from the cleaned dataset.
        """
        # Normalise status string and V2X flag
        status = row.get('cp_status', 'unknown')
        status = str(status).strip().lower() if isinstance(status, str) else 'unknown'
        # Determine V2X flag numeric value
        vx = row.get('vx_flag', 0)
        try:
            vx_val = float(vx)
        except Exception:
            vx_val = 0
        # Priority 1: V2X sites (operational or under construction)
        if vx_val >= 1 and status in {'open', 'cwys'}:
            return 'V2X Chargepoint'
        # Normalise name for comparison (applied after checking V2X)
        name = str(row.get('charge_point_location', '')).strip().lower()
        # Priority 2: Building‑supplied sites (if not V2X)
        if name in building_sites_set:
            return 'Building-supplied Charger'
        # Priority 3: Other chargepoints - include only fully open (non‑V2X)
        if vx_val < 1 and status == 'open':
            return 'Other Chargepoint'
        # Exclude all other combinations (inactive or potential sites)
        return None
    df['site_category'] = df.apply(classify_site, axis=1)
    # Drop rows where classification is None (inactive or potential sites)
    df = df[~df['site_category'].isna()].copy()
    # Select required fields; drop duplicates by location
    required = ['charge_point_location', 'site_category', 'latitude', 'longitude']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for chargepoints dataset: {missing}")
    df_clean = df[required].drop_duplicates(subset=['charge_point_location']).copy()
    # Convert coordinates to numeric and drop rows with invalid values
    df_clean['latitude'] = pd.to_numeric(df_clean['latitude'], errors='coerce')
    df_clean['longitude'] = pd.to_numeric(df_clean['longitude'], errors='coerce')
    df_clean = df_clean.dropna(subset=['latitude', 'longitude'])
    # Save cleaned chargepoints as CSV
    df_clean.to_csv(output_path, index=False, encoding='utf-8')
    print(f"Saved cleaned chargepoints to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Clean raw CMS chargepoint exports for the dashboard.')
    parser.add_argument('--input', required=True, help='Path to the raw CSV file')
    parser.add_argument('--output', default='data/all_charging_sites.csv', help='Path to save the cleaned CSV')
    args = parser.parse_args()
    clean_chargepoints(args.input, args.output)


if __name__ == '__main__':
    main()