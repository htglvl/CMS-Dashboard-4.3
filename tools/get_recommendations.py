"""Run the recommendation engine and return results.

Usage:
    python tools/get_recommendations.py
    python tools/get_recommendations.py --type v2x
    python tools/get_recommendations.py --type chargepoint
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS_RF = PROJECT_ROOT / "models" / "predictions_randomforest.csv"
OUTAGES_FILE = PROJECT_ROOT / "data" / "df_cleaned.csv"
CHARGING_SITES_FILE = PROJECT_ROOT / "data" / "all_charging_sites.csv"


def main():
    parser = argparse.ArgumentParser(description="Run recommendation engine.")
    parser.add_argument("--type", type=str, default="all", choices=["v2x", "chargepoint", "all"])
    args = parser.parse_args()

    try:
        from advanced_charts.recommendation_engine import RecommendationEngine

        if PREDICTIONS_RF.exists():
            predictions = pd.read_csv(PREDICTIONS_RF)
        else:
            xgb = PROJECT_ROOT / "models" / "predictions_xgboost.csv"
            predictions = pd.read_csv(xgb) if xgb.exists() else None
        if predictions is None:
            raise FileNotFoundError("No prediction files found in models/")

        outages = pd.read_csv(OUTAGES_FILE, low_memory=False, parse_dates=["incident_date_time"])
        charging_sites = pd.read_csv(CHARGING_SITES_FILE) if CHARGING_SITES_FILE.exists() else None

        engine = RecommendationEngine(predictions, outages, charging_sites)

        recs_list = []
        if args.type in ("v2x", "all"):
            recs_list.extend(engine.charging_station_recommendations())
        if args.type in ("chargepoint", "all"):
            recs_list.extend(engine.chargepoint_recommendations())
        if args.type == "all":
            recs_list.extend(engine.grid_resilience_recommendations())
            recs_list.extend(engine.community_impact_recommendations())

        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        recs_list.sort(key=lambda r: priority_order.get(r.priority, 9))

        recommendations = []
        for rec in recs_list:
            recommendations.append({
                "category": rec.category,
                "priority": rec.priority,
                "title": rec.title,
                "detail": rec.detail,
                "lat": rec.location[0] if rec.location else None,
                "lon": rec.location[1] if rec.location else None,
                "score": round(rec.score, 4),
            })

        report = engine.generate_all_insights()
        output = {"recommendations": recommendations, "summary": report.summary}
        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
