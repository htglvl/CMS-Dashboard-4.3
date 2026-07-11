"""Forecast potential outages by season based on historical data.

Uses historical seasonal outage counts from reliable years (100+ outages/year)
to produce mean, median, and range forecasts for each season.

Usage:
    python tools/forecast_outages_by_season.py
    python tools/forecast_outages_by_season.py --season Winter
    python tools/forecast_outages_by_season.py --year 2027
    python tools/forecast_outages_by_season.py --district Lancaster
    python tools/forecast_outages_by_season.py --cause Weather
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"

# Years with at least 100 outages (reliable reporting)
MIN_OUTAGES_PER_YEAR = 100

SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]


def load_and_filter(df: pd.DataFrame, district: str = None, cause: str = None) -> pd.DataFrame:
    """Apply optional filters to the outage data."""
    if district:
        df = df[df["district_name"].str.lower().str.contains(district.lower(), na=False)]
    if cause:
        df = df[df["direct_cause_category"].str.lower().str.contains(cause.lower(), na=False)]
    return df


def compute_seasonal_forecast(df: pd.DataFrame) -> dict:
    """Compute seasonal outage count statistics from historical data."""
    # Filter to reliable years
    year_counts = df.groupby("year").size()
    reliable_years = year_counts[year_counts >= MIN_OUTAGES_PER_YEAR].index
    df_reliable = df[df["year"].isin(reliable_years)]

    if df_reliable.empty:
        return {"error": "No reliable years found in the data"}

    # Count outages per season per year
    seasonal_counts = df_reliable.groupby(["year", "season"]).size().unstack(fill_value=0)

    # Ensure all seasons present
    for s in SEASON_ORDER:
        if s not in seasonal_counts.columns:
            seasonal_counts[s] = 0

    # Compute stats per season
    forecasts = {}
    for season in SEASON_ORDER:
        counts = seasonal_counts[season].values
        mean_val = float(np.mean(counts))
        median_val = float(np.median(counts))
        std_val = float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0
        min_val = int(np.min(counts))
        max_val = int(np.max(counts))

        # Forecast range: mean ± 1 std dev (clamped to 0)
        low = max(0, round(mean_val - std_val))
        high = round(mean_val + std_val)

        forecasts[season] = {
            "historical_mean": round(mean_val, 1),
            "historical_median": round(median_val, 1),
            "historical_std": round(std_val, 1),
            "historical_min": min_val,
            "historical_max": max_val,
            "forecast_low": low,
            "forecast_expected": round(mean_val),
            "forecast_high": high,
            "years_of_data": len(counts),
        }

    return forecasts


def compute_duration_stats(df: pd.DataFrame) -> dict:
    """Compute average outage duration per season."""
    stats = {}
    for season in SEASON_ORDER:
        season_df = df[df["season"] == season]
        if season_df.empty:
            continue
        durations = pd.to_numeric(season_df["duration-hours"], errors="coerce").dropna()
        stats[season] = {
            "median_duration_hours": round(float(durations.median()), 2),
            "mean_duration_hours": round(float(durations.mean()), 2),
        }
    return stats


def compute_cause_breakdown(df: pd.DataFrame) -> dict:
    """Compute top causes per season."""
    breakdown = {}
    for season in SEASON_ORDER:
        season_df = df[df["season"] == season]
        if season_df.empty:
            continue
        causes = season_df["direct_cause_category"].value_counts().head(5)
        breakdown[season] = {str(k): int(v) for k, v in causes.items()}
    return breakdown


def main():
    parser = argparse.ArgumentParser(description="Forecast outages by season.")
    parser.add_argument("--season", type=str, choices=SEASON_ORDER,
                        help="Forecast for a specific season only")
    parser.add_argument("--year", type=int, default=None,
                        help="Target forecast year (informational only)")
    parser.add_argument("--district", type=str, default=None,
                        help="Filter by district name")
    parser.add_argument("--cause", type=str, default=None,
                        help="Filter by direct cause category")
    parser.add_argument("--include-duration", action="store_true",
                        help="Include average duration stats per season")
    parser.add_argument("--include-causes", action="store_true",
                        help="Include top causes per season")
    args = parser.parse_args()

    try:
        if not OUTAGES_FILE.exists():
            raise FileNotFoundError(f"Outage data not found: {OUTAGES_FILE}")

        df = pd.read_csv(OUTAGES_FILE, low_memory=False)
        df = load_and_filter(df, args.district, args.cause)

        if df.empty:
            print(json.dumps({"error": "No outage data found matching filters"}, indent=2))
            sys.exit(1)

        # Compute forecasts
        forecasts = compute_seasonal_forecast(df)

        if "error" in forecasts:
            print(json.dumps(forecasts, indent=2))
            sys.exit(1)

        # Filter to single season if requested
        if args.season:
            forecasts = {args.season: forecasts[args.season]}

        # Build output
        total_historical = len(df)
        reliable_year_counts = df.groupby("year").size()
        reliable_years = reliable_year_counts[reliable_year_counts >= MIN_OUTAGES_PER_YEAR].index.tolist()

        output = {
            "summary": {
                "total_outages_in_dataset": total_historical,
                "reliable_years_used": sorted(reliable_years),
                "min_outages_per_year_threshold": MIN_OUTAGES_PER_YEAR,
            },
            "forecasts": forecasts,
        }

        if args.year:
            output["summary"]["target_year"] = args.year

        if args.district:
            output["summary"]["district_filter"] = args.district
        if args.cause:
            output["summary"]["cause_filter"] = args.cause

        if args.include_duration:
            output["duration_stats"] = compute_duration_stats(df)

        if args.include_causes:
            output["top_causes"] = compute_cause_breakdown(df)

        print(json.dumps(output, indent=2, default=str))

    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
