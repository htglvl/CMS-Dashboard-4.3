"""
Geospatial Risk Model for unplanned electricity outages.

Uses historic outage data from Electricity North West to predict outage
risk level (High / Medium / Low) per grid cell.  Two models are trained:

* **Random Forest** — for explainability (feature importance).
* **XGBoost** — for higher accuracy on tabular data.

The feature engineering pipeline grids the study area into ~1 km cells
and computes temporal, severity, and spatial features from the outage
catalogue.  Predictions include a confidence score (class probability)
and per-cell probability estimates.

Usage
-----
    python risk_model.py                # Train + evaluate + save
    python risk_model.py --predict      # Load saved models, predict all cells
    python risk_model.py --evaluate     # Print evaluation metrics only

Environment
-----------
Requires ``df_cleaned.csv`` in the same directory.
Models are saved to ``models/rf_model.pkl`` and ``models/xgb_model.pkl``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from math import radians, sin, cos, sqrt, atan2

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_FILE = Path(__file__).parent.parent / "data" / "df_cleaned.csv"
MODELS_DIR = Path(__file__).parent.parent / "models"
RF_MODEL_PATH = MODELS_DIR / "rf_model.pkl"
XGB_MODEL_PATH = MODELS_DIR / "xgb_model.pkl"
FEATURES_CACHE = Path(__file__).parent.parent / "data" / "grid_features_cache.pkl"

# Grid cell size in degrees (~0.01° ≈ 1 km at UK latitudes)
CELL_SIZE = 0.01

# Risk class labels
RISK_LABELS = ["Low", "Medium", "High"]

# ---------------------------------------------------------------------------
# Haversine helper
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorised Haversine distance in km between a point and arrays of points."""
    R = 6371.0
    lat1_r, lon1_r = radians(lat1), radians(lon1)
    lat2_r = np.radians(lat2)
    lon2_r = np.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


def build_grid_features(outages: pd.DataFrame, cell_size: float = CELL_SIZE) -> pd.DataFrame:
    """Compute per-grid-cell features from the outage catalogue.

    Parameters
    ----------
    outages : pd.DataFrame
        Cleaned outage data (must have ``latitude``, ``longitude``,
        ``duration-hours``, ``total_customer_minutes_lost``,
        ``incident_date_time``, ``direct_cause_category``).
    cell_size : float
        Grid cell size in degrees.

    Returns
    -------
    pd.DataFrame
        One row per grid cell with engineered features.
    """
    df = outages.copy()

    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(df["incident_date_time"]):
        df["incident_date_time"] = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)

    # Assign grid cell
    df["cell_lat"] = (df["latitude"] / cell_size).round() * cell_size
    df["cell_lon"] = (df["longitude"] / cell_size).round() * cell_size

    # Temporal features
    df["month"] = df["incident_date_time"].dt.month
    df["hour"] = df["incident_date_time"].dt.hour
    df["is_winter"] = df["month"].isin([12, 1, 2])
    df["is_night"] = (df["hour"] >= 22) | (df["hour"] < 6)

    # Ensure numeric
    df["duration-hours"] = pd.to_numeric(df["duration-hours"], errors="coerce").fillna(0)
    df["total_customer_minutes_lost"] = pd.to_numeric(
        df["total_customer_minutes_lost"], errors="coerce"
    ).fillna(0)

    # Exceptional event flag
    if "is_exceptional_event" in df.columns:
        df["is_exceptional"] = df["is_exceptional_event"].fillna(False).astype(bool)
    else:
        df["is_exceptional"] = False

    # Group by cell
    grouped = df.groupby(["cell_lat", "cell_lon"])

    features = grouped.agg(
        outage_count=("duration-hours", "size"),
        avg_duration=("duration-hours", "mean"),
        std_duration=("duration-hours", "std"),
        total_customer_hours=("total_customer_minutes_lost", lambda x: x.sum() / 60),
        winter_ratio=("is_winter", "mean"),
        night_ratio=("is_night", "mean"),
        exceptional_ratio=("is_exceptional", "mean"),
        cause_diversity=("direct_cause_category", "nunique"),
    ).reset_index()

    features.rename(columns={"cell_lat": "lat", "cell_lon": "lon"}, inplace=True)
    features["std_duration"] = features["std_duration"].fillna(0)

    # Nearest-substation distance (approximate: use mean lat/lon per cell)
    if "primary_substation" in df.columns:
        substation_locs = (
            df.dropna(subset=["primary_substation"])
            .groupby("primary_substation")[["latitude", "longitude"]]
            .mean()
            .values
        )
        if len(substation_locs) > 0:
            distances = []
            for _, row in features.iterrows():
                dists = haversine_km(row["lat"], row["lon"], substation_locs[:, 0], substation_locs[:, 1])
                distances.append(dists.min())
            features["nearest_substation_km"] = distances
        else:
            features["nearest_substation_km"] = 0.0
    else:
        features["nearest_substation_km"] = 0.0

    return features


_features_mem_cache: pd.DataFrame | None = None
_features_mem_mtime: float = 0.0


def build_grid_features_cached(outages: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    """Build grid features with persistent + in-memory pickle cache."""
    global _features_mem_cache, _features_mem_mtime
    import joblib

    if not force and FEATURES_CACHE.exists():
        mtime = FEATURES_CACHE.stat().st_mtime
        if _features_mem_cache is not None and mtime == _features_mem_mtime:
            return _features_mem_cache
        log.info("Loading grid features from cache: %s", FEATURES_CACHE)
        _features_mem_cache = joblib.load(FEATURES_CACHE)
        _features_mem_mtime = mtime
        return _features_mem_cache

    features = build_grid_features(outages)
    FEATURES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(features, FEATURES_CACHE)
    _features_mem_cache = features
    _features_mem_mtime = FEATURES_CACHE.stat().st_mtime
    log.info("Grid features cached to %s (%d cells)", FEATURES_CACHE, len(features))
    return features


def invalidate_features_cache():
    """Delete the grid features cache (called after new data fetch)."""
    global _features_mem_cache, _features_mem_mtime
    if FEATURES_CACHE.exists():
        FEATURES_CACHE.unlink()
        log.info("Grid features cache invalidated: %s", FEATURES_CACHE)
    _features_mem_cache = None
    _features_mem_mtime = 0.0


def assign_risk_labels(features: pd.DataFrame) -> pd.DataFrame:
    """Assign risk labels using quantile-based binning on outage_count.

    Parameters
    ----------
    features : pd.DataFrame
        Output of :func:`build_grid_features`.

    Returns
    -------
    pd.DataFrame
        Features with an added ``risk_level`` column (categorical).
    """
    df = features.copy()
    df["risk_level"] = pd.qcut(
        df["outage_count"],
        q=3,
        labels=RISK_LABELS,
        duplicates="drop",
    )
    return df


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "outage_count",
    "avg_duration",
    "std_duration",
    "total_customer_hours",
    "winter_ratio",
    "night_ratio",
    "exceptional_ratio",
    "cause_diversity",
    "nearest_substation_km",
]


def get_xy(features: pd.DataFrame):
    """Return (X, y) arrays from a features DataFrame."""
    X = features[FEATURE_COLS].values
    y = features["risk_level"].values
    return X, y


def train_random_forest(X_train, y_train, random_state: int = 42):
    """Train a Random Forest classifier."""
    from sklearn.ensemble import RandomForestClassifier

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def train_xgboost(X_train, y_train, random_state: int = 42):
    """Train an XGBoost classifier."""
    from xgboost import XGBClassifier
    from sklearn.preprocessing import LabelEncoder

    le = LabelEncoder()
    y_encoded = le.fit_transform(y_train)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_train, y_encoded)
    return model, le


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_model(model, X_test, y_test, label_encoder=None, model_name: str = "Model"):
    """Print evaluation metrics."""
    from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

    if label_encoder is not None:
        y_pred = label_encoder.inverse_transform(model.predict(X_test))
    else:
        y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    log.info("%s accuracy: %.3f", model_name, acc)
    log.info("\n%s", classification_report(y_test, y_pred, target_names=RISK_LABELS))

    cm = confusion_matrix(y_test, y_pred, labels=RISK_LABELS)
    log.info("Confusion matrix:\n%s", cm)

    return {"accuracy": acc, "y_pred": y_pred}


def get_feature_importance(model, model_name: str = "Model") -> pd.DataFrame:
    """Return feature importance as a DataFrame."""
    importances = model.feature_importances_
    fi = pd.DataFrame({"feature": FEATURE_COLS, "importance": importances})
    fi.sort_values("importance", ascending=False, inplace=True)
    fi.reset_index(drop=True, inplace=True)
    log.info("%s feature importance:\n%s", model_name, fi.to_string(index=False))
    return fi


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------


def predict_cells(model, features: pd.DataFrame, label_encoder=None) -> pd.DataFrame:
    """Predict risk level and confidence for each grid cell.

    Returns
    -------
    pd.DataFrame
        Columns: lat, lon, risk_level, confidence, prob_low, prob_medium, prob_high
    """
    X = features[FEATURE_COLS].values
    proba = model.predict_proba(X)
    classes = model.classes_ if label_encoder is None else label_encoder.classes_

    if label_encoder is not None:
        pred_labels = label_encoder.inverse_transform(model.predict(X))
    else:
        pred_labels = model.predict(X)

    result = features[["lat", "lon"]].copy()
    result["risk_level"] = pred_labels
    result["confidence"] = proba.max(axis=1)

    for i, cls in enumerate(classes):
        result[f"prob_{cls.lower()}"] = proba[:, i]

    return result


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def save_models(rf_model, xgb_model, xgb_label_encoder):
    """Persist trained models to disk."""
    import joblib

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(rf_model, RF_MODEL_PATH)
    joblib.dump({"model": xgb_model, "label_encoder": xgb_label_encoder}, XGB_MODEL_PATH)
    log.info("Models saved to %s", MODELS_DIR)


def load_models():
    """Load persisted models from disk.

    If model files are missing, trains them from ``df_cleaned.csv`` and
    saves them to disk before loading.

    Returns
    -------
    tuple
        (rf_model, xgb_model, xgb_label_encoder)
    """
    import joblib

    if not RF_MODEL_PATH.exists() or not XGB_MODEL_PATH.exists():
        log.info("Model files not found — training from %s", DATA_FILE)
        _train_and_save()

    rf_model = joblib.load(RF_MODEL_PATH)
    xgb_bundle = joblib.load(XGB_MODEL_PATH)
    return rf_model, xgb_bundle["model"], xgb_bundle["label_encoder"]


def _train_and_save():
    """Train both models on the full dataset and save to disk."""
    from sklearn.model_selection import train_test_split

    outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
    log.info("Training models on %d outage records...", len(outages))

    features = build_grid_features(outages)
    features = assign_risk_labels(features)
    X, y = get_xy(features)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    rf_model = train_random_forest(X_train, y_train)
    evaluate_model(rf_model, X_test, y_test, model_name="Random Forest")
    get_feature_importance(rf_model, "Random Forest")

    xgb_model, xgb_le = train_xgboost(X_train, y_train)
    evaluate_model(xgb_model, X_test, y_test, xgb_le, "XGBoost")
    get_feature_importance(xgb_model, "XGBoost")

    save_models(rf_model, xgb_model, xgb_le)

    # Also save predictions
    for name, model, le in [("RandomForest", rf_model, None), ("XGBoost", xgb_model, xgb_le)]:
        preds = predict_cells(model, features, le)
        out_path = MODELS_DIR / f"predictions_{name.lower()}.csv"
        preds.to_csv(out_path, index=False)
        log.info("%s predictions saved to %s (%d cells)", name, out_path, len(preds))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Geospatial risk model for unplanned outages.")
    parser.add_argument("--predict", action="store_true", help="Load models and predict all cells.")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate models only.")
    args = parser.parse_args()

    if args.predict:
        rf_model, xgb_model, xgb_le = load_models()
        outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
        features = build_grid_features(outages)
        features = assign_risk_labels(features)

        for name, model, le in [("RandomForest", rf_model, None), ("XGBoost", xgb_model, xgb_le)]:
            preds = predict_cells(model, features, le)
            out_path = MODELS_DIR / f"predictions_{name.lower()}.csv"
            preds.to_csv(out_path, index=False)
            log.info("%s predictions saved to %s (%d cells)", name, out_path, len(preds))
        return

    # --- Train ---
    log.info("Loading data from %s", DATA_FILE)
    outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
    log.info("Loaded %d outage records", len(outages))

    features = build_grid_features(outages)
    features = assign_risk_labels(features)
    log.info("Grid features: %d cells", len(features))
    log.info("Risk distribution:\n%s", features["risk_level"].value_counts().to_string())

    X, y = get_xy(features)

    from sklearn.model_selection import train_test_split, cross_val_score

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Random Forest
    log.info("Training Random Forest...")
    rf_model = train_random_forest(X_train, y_train)
    rf_results = evaluate_model(rf_model, X_test, y_test, model_name="Random Forest")
    get_feature_importance(rf_model, "Random Forest")

    # XGBoost
    log.info("Training XGBoost...")
    xgb_model, xgb_le = train_xgboost(X_train, y_train)
    xgb_results = evaluate_model(xgb_model, X_test, y_test, xgb_le, "XGBoost")
    get_feature_importance(xgb_model, "XGBoost")

    # Cross-validation
    log.info("5-fold cross-validation...")
    rf_cv = cross_val_score(rf_model, X, y, cv=5, scoring="accuracy")
    log.info("RF CV accuracy: %.3f ± %.3f", rf_cv.mean(), rf_cv.std())

    # Save
    if not args.evaluate:
        save_models(rf_model, xgb_model, xgb_le)

        # Generate and save predictions
        for name, model, le in [("RandomForest", rf_model, None), ("XGBoost", xgb_model, xgb_le)]:
            preds = predict_cells(model, features, le)
            out_path = MODELS_DIR / f"predictions_{name.lower()}.csv"
            preds.to_csv(out_path, index=False)
            log.info("%s predictions saved to %s (%d cells)", name, out_path, len(preds))

    log.info("Done.")


if __name__ == "__main__":
    main()
