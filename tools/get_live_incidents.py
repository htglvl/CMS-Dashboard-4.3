"""Fetch live incidents from the ENW API.

Usage:
    python tools/get_live_incidents.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import pandas as pd


def main():
    try:
        from data.fetch_live_incidents import fetch_live_incidents
        df = fetch_live_incidents()

        if df.empty:
            output = {"count": 0, "incidents": [], "message": "No active incidents"}
        else:
            incidents = []
            for _, row in df.iterrows():
                incident = {}
                for col in ["incident_num", "incident_type", "outage_time",
                            "customers_affected", "customers_off_supply",
                            "incident_status", "estimated_restoration_time",
                            "latitude", "longitude"]:
                    val = row.get(col)
                    if pd.isna(val):
                        incident[col] = None
                    elif isinstance(val, pd.Timestamp):
                        incident[col] = str(val)
                    else:
                        incident[col] = val
                incidents.append(incident)
            output = {"count": len(incidents), "incidents": incidents}

        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
