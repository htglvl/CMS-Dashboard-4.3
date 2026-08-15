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

# Grid cell size in degrees (~0.02° ≈ 2 km at UK latitudes)
CELL_SIZE = 0.02

# Duration outlier cap (hours) — prevents extreme outliers from distorting avg/std
DURATION_CAP_HOURS = 168.0  # 1 week

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


def build_grid_features(outages: pd.DataFrame, cell_size: float = CELL_SIZE,
                        start_date=None, end_date=None,
                        grid_cells=None) -> pd.DataFrame:
    """Compute per-grid-cell features from the outage catalogue.

    Features include temporal, severity, spatial, and infrastructure metrics.
    Outlier durations are capped and skewed features are log-transformed.

    Parameters
    ----------
    outages : pd.DataFrame
        Cleaned outage data.
    cell_size : float
        Grid cell size in degrees.
    start_date, end_date : str or None
        Date window filters.
    grid_cells : pd.DataFrame or None
        Fixed grid definition (lat, lon columns).

    Returns
    -------
    pd.DataFrame
        One row per grid cell with engineered features.
    """
    df = outages.copy()

    # Ensure datetime
    if not pd.api.types.is_datetime64_any_dtype(df["incident_date_time"]):
        df["incident_date_time"] = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)

    # Filter to date window
    if start_date is not None:
        start_ts = pd.Timestamp(start_date)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        df = df[df["incident_date_time"] >= start_ts]
    if end_date is not None:
        end_ts = pd.Timestamp(end_date)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize("UTC")
        df = df[df["incident_date_time"] < end_ts]

    # If no outages in window, return grid_cells with zeroed features
    if df.empty and grid_cells is not None:
        result = grid_cells[["lat", "lon"]].copy()
        for col in FEATURE_COLS:
            result[col] = 0.0
        return result
    elif df.empty:
        return pd.DataFrame(columns=["lat", "lon"] + FEATURE_COLS)

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

    # Cap outlier durations (prevents extreme values from distorting avg/std)
    df["duration_capped"] = df["duration-hours"].clip(upper=DURATION_CAP_HOURS)

    # Exceptional event flag
    if "is_exceptional_event" in df.columns:
        df["is_exceptional"] = df["is_exceptional_event"].fillna(False).astype(bool)
    else:
        df["is_exceptional"] = False

    # Group by cell
    grouped = df.groupby(["cell_lat", "cell_lon"])

    features = grouped.agg(
        outage_count=("duration_capped", "size"),
        avg_duration=("duration_capped", "mean"),
        std_duration=("duration_capped", "std"),
        total_customer_hours=("total_customer_minutes_lost", lambda x: x.sum() / 60),
        max_duration=("duration_capped", "max"),
        winter_ratio=("is_winter", "mean"),
        night_ratio=("is_night", "mean"),
        exceptional_ratio=("is_exceptional", "mean"),
        cause_diversity=("direct_cause_category", "nunique"),
    ).reset_index()

    features.rename(columns={"cell_lat": "lat", "cell_lon": "lon"}, inplace=True)
    features["std_duration"] = features["std_duration"].fillna(0)

    # Log-transform skewed features (add 1 to avoid log(0))
    features["log_total_customer_hours"] = np.log1p(features["total_customer_hours"])
    features["log_avg_duration"] = np.log1p(features["avg_duration"])

    # Nearest-substation distance
    features["nearest_substation_km"] = 0.0
    if "primary_substation" in df.columns:
        substation_locs = (
            df.dropna(subset=["primary_substation"])
            .groupby("primary_substation")[["latitude", "longitude"]]
            .mean()
        )
        if len(substation_locs) > 0:
            sub_coords = substation_locs.values
            distances = []
            for _, row in features.iterrows():
                dists = haversine_km(row["lat"], row["lon"], sub_coords[:, 0], sub_coords[:, 1])
                distances.append(float(dists.min()))
            features["nearest_substation_km"] = distances

    # Spatial features: count outages in neighboring cells (3x3 grid)
    # Build a lookup of (lat, lon) -> outage_count
    cell_counts = features.set_index(["lat", "lon"])["outage_count"].to_dict()
    neighbor_counts = []
    neighbor_avg_durations = []
    for _, row in features.iterrows():
        lat, lon = row["lat"], row["lon"]
        total_neighbors = 0.0
        total_dur_neighbors = 0.0
        count_neighbors = 0
        for dlat in [-cell_size, 0, cell_size]:
            for dlon in [-cell_size, 0, cell_size]:
                if dlat == 0 and dlon == 0:
                    continue  # skip self
                key = (round(lat + dlat, 6), round(lon + dlon, 6))
                if key in cell_counts:
                    total_neighbors += cell_counts[key]
                    count_neighbors += 1
        neighbor_counts.append(total_neighbors)
    features["neighbor_outage_count"] = neighbor_counts

    # If a fixed grid was provided, ensure all cells are present
    if grid_cells is not None:
        features = grid_cells[["lat", "lon"]].merge(features, on=["lat", "lon"], how="left")
        for col in FEATURE_COLS:
            features[col] = features[col].fillna(0)

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

    Uses 33rd/67th percentile thresholds of non-zero outage counts
    for more balanced class distribution than median split.

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
    non_zero = df.loc[df["outage_count"] > 0, "outage_count"]
    if len(non_zero) == 0:
        df["risk_level"] = "Low"
    else:
        # Use 33rd/67th percentiles for more balanced classes
        q33 = non_zero.quantile(0.33)
        q67 = non_zero.quantile(0.67)
        df["risk_level"] = "Low"
        df.loc[df["outage_count"] > 0, "risk_level"] = "Medium"
        df.loc[df["outage_count"] > q67, "risk_level"] = "High"
    df["risk_level"] = pd.Categorical(df["risk_level"], categories=RISK_LABELS, ordered=True)
    return df


def build_training_samples(outages: pd.DataFrame,
                           feature_months: int = 12,
                           prediction_months: int = 3,
                           step_months: int = 1,
                           start_year: int = 2000,
                           cell_size: float = CELL_SIZE) -> pd.DataFrame:
    """Build training data using a sliding window approach.

    For each cutoff date (monthly steps), compute features from the
    preceding *feature_months* and labels from the following
    *prediction_months*.  Labels are Low/Medium/High based on quantile
    binning of outage count in the prediction window.

    Parameters
    ----------
    outages : pd.DataFrame
        Full outage dataset with ``incident_date_time`` column.
    feature_months : int
        Number of months of history to compute features from.
    prediction_months : int
        Number of months ahead to compute labels from.
    step_months : int
        Months to advance the window each step.
    start_year : int
        First year to generate windows from (needs enough history).
    cell_size : float
        Grid cell size in degrees.

    Returns
    -------
    pd.DataFrame
        Columns: lat, lon, cutoff_date, FEATURE_COLS..., risk_level
    """
    df = outages.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["incident_date_time"]):
        df["incident_date_time"] = pd.to_datetime(df["incident_date_time"], errors="coerce", utc=True)

    # Define the fixed grid from the full dataset
    df["cell_lat"] = (df["latitude"] / cell_size).round() * cell_size
    df["cell_lon"] = (df["longitude"] / cell_size).round() * cell_size
    grid_cells = df.groupby(["cell_lat", "cell_lon"]).size().reset_index()[["cell_lat", "cell_lon"]]
    grid_cells.rename(columns={"cell_lat": "lat", "cell_lon": "lon"}, inplace=True)

    # Date range for sliding windows
    min_date = df["incident_date_time"].min()
    max_date = df["incident_date_time"].max()

    # First cutoff: start of (start_year + 1) so feature window has full 12 months
    first_cutoff = pd.Timestamp(f"{start_year + 1}-01-01", tz="UTC")
    # Last cutoff: enough room for prediction_months
    last_cutoff = max_date - pd.DateOffset(months=prediction_months)

    if first_cutoff >= last_cutoff:
        log.warning("Not enough data for sliding window (data spans %s to %s)", min_date, max_date)
        return pd.DataFrame()

    samples = []
    cutoff = first_cutoff
    while cutoff <= last_cutoff:
        feature_start = cutoff - pd.DateOffset(months=feature_months)
        feature_end = cutoff
        label_start = cutoff
        label_end = cutoff + pd.DateOffset(months=prediction_months)

        # Build features from the feature window
        features = build_grid_features(
            outages, cell_size=cell_size,
            start_date=feature_start, end_date=feature_end,
            grid_cells=grid_cells,
        )

        # Count outages in the prediction window per cell
        label_outages = df[
            (df["incident_date_time"] >= label_start) &
            (df["incident_date_time"] < label_end)
        ]
        label_counts = (
            label_outages
            .groupby(["cell_lat", "cell_lon"])
            .size()
            .reset_index(name="future_outage_count")
        )
        label_counts.rename(columns={"cell_lat": "lat", "cell_lon": "lon"}, inplace=True)

        # Merge features with labels
        merged = features.merge(label_counts, on=["lat", "lon"], how="left")
        merged["future_outage_count"] = merged["future_outage_count"].fillna(0)

        # Assign risk labels using 33rd/67th percentile thresholds
        non_zero = merged.loc[merged["future_outage_count"] > 0, "future_outage_count"]
        if len(non_zero) == 0:
            merged["risk_level"] = "Low"
        else:
            q67 = non_zero.quantile(0.67)
            merged["risk_level"] = "Low"
            merged.loc[merged["future_outage_count"] > 0, "risk_level"] = "Medium"
            merged.loc[merged["future_outage_count"] > q67, "risk_level"] = "High"
        merged["risk_level"] = pd.Categorical(merged["risk_level"], categories=RISK_LABELS, ordered=True)

        merged["cutoff_date"] = cutoff
        samples.append(merged)

        cutoff += pd.DateOffset(months=step_months)

    if not samples:
        return pd.DataFrame()

    result = pd.concat(samples, ignore_index=True)
    # Keep only cells that have at least some outage history
    result = result[result[FEATURE_COLS].sum(axis=1) > 0]
    log.info("Built %d training samples from %d windows (%d cells per window)",
             len(result), len(samples), len(grid_cells))
    return result
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "outage_count",
    "avg_duration",
    "std_duration",
    "total_customer_hours",
    "max_duration",
    "log_avg_duration",
    "log_total_customer_hours",
    "winter_ratio",
    "night_ratio",
    "exceptional_ratio",
    "cause_diversity",
    "nearest_substation_km",
    "neighbor_outage_count",
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
    """Train an XGBoost classifier with class weight balancing (deep)."""
    from xgboost import XGBClassifier
    from sklearn.preprocessing import LabelEncoder
    from sklearn.utils.class_weight import compute_class_weight

    le = LabelEncoder()
    y_encoded = le.fit_transform(y_train)

    # Compute class weights to handle imbalance
    classes = np.unique(y_encoded)
    class_weights = compute_class_weight("balanced", classes=classes, y=y_encoded)
    weight_map = dict(zip(classes, class_weights))
    sample_weights = np.array([weight_map[y] for y in y_encoded])

    model = XGBClassifier(
        n_estimators=500,
        max_depth=10,
        learning_rate=0.03,
        subsample=0.7,
        colsample_bytree=0.7,
        min_child_weight=1,
        gamma=0.2,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=random_state,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_train, y_encoded, sample_weight=sample_weights)
    return model, le


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_model(model, X_test, y_test, label_encoder=None, model_name: str = "Model"):
    """Print evaluation metrics and return them."""
    from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score, precision_score, recall_score

    if label_encoder is not None:
        y_pred = label_encoder.inverse_transform(model.predict(X_test))
    else:
        y_pred = model.predict(X_test)

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    precision_macro = precision_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    recall_macro = recall_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)

    log.info("%s accuracy: %.3f, F1(macro): %.3f, precision(macro): %.3f, recall(macro): %.3f",
             model_name, acc, f1_macro, precision_macro, recall_macro)
    log.info("\n%s", classification_report(y_test, y_pred, labels=RISK_LABELS, target_names=RISK_LABELS, zero_division=0))

    cm = confusion_matrix(y_test, y_pred, labels=RISK_LABELS)
    log.info("Confusion matrix:\n%s", cm)

    return {
        "accuracy": acc,
        "f1_macro": f1_macro,
        "precision_macro": precision_macro,
        "recall_macro": recall_macro,
        "y_pred": y_pred,
    }


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

    # Remove old files before writing new ones
    for path in [RF_MODEL_PATH, XGB_MODEL_PATH]:
        if path.exists():
            path.unlink()

    joblib.dump(rf_model, RF_MODEL_PATH)
    joblib.dump({"model": xgb_model, "label_encoder": xgb_label_encoder}, XGB_MODEL_PATH)
    log.info("Models saved to %s", MODELS_DIR)


def load_models():
    """Load persisted models from disk.

    If model files are missing or older than 3 months, trains them from
    ``df_cleaned.csv`` and saves them to disk before loading.

    Returns
    -------
    tuple
        (rf_model, xgb_model, xgb_label_encoder)
    """
    import joblib
    from advanced_charts.cache_utils import is_cache_stale

    if (not RF_MODEL_PATH.exists() or not XGB_MODEL_PATH.exists()
            or is_cache_stale(RF_MODEL_PATH) or is_cache_stale(XGB_MODEL_PATH)):
        log.info("Model files missing or stale — training from %s", DATA_FILE)
        _train_and_save()

    rf_model = joblib.load(RF_MODEL_PATH)
    xgb_bundle = joblib.load(XGB_MODEL_PATH)
    return rf_model, xgb_bundle["model"], xgb_bundle["label_encoder"]


def _train_and_save():
    """Train both models using walk-forward validation and save to disk.

    Uses 12-month feature windows, 3-month prediction windows, 1-month step.
    Walk-forward: 5 chronological folds, train on past, validate on future.
    Final production models trained on ALL data.
    """
    outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
    log.info("Training models on %d outage records...", len(outages))

    # Build sliding-window training samples
    samples = build_training_samples(outages)
    if samples.empty:
        log.error("No training samples generated — check data range")
        return

    # Split into 5 chronological folds by cutoff_date
    cutoff_dates = samples["cutoff_date"].sort_values().unique()
    n_folds = 5
    fold_edges = np.array_split(np.arange(len(cutoff_dates)), n_folds)
    fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

    log.info("Walk-forward validation with %d folds", n_folds)
    log.info("Cutoff dates range: %s to %s", cutoff_dates[0], cutoff_dates[-1])

    # Walk-forward: train on folds 0..k-1, validate on fold k
    rf_metrics = []
    xgb_metrics = []

    for k in range(1, n_folds):
        train_mask = samples["cutoff_date"] <= fold_cutoffs[k - 1]
        val_mask = (samples["cutoff_date"] > fold_cutoffs[k - 1]) & \
                   (samples["cutoff_date"] <= fold_cutoffs[k])

        train_data = samples[train_mask]
        val_data = samples[val_mask]

        if train_data.empty or val_data.empty:
            continue

        X_train, y_train = get_xy(train_data)
        X_val, y_val = get_xy(val_data)

        log.info("Fold %d: train=%d, val=%d (split at %s)",
                 k, len(train_data), len(val_data), fold_cutoffs[k - 1])

        # RF
        rf = train_random_forest(X_train, y_train)
        rf_result = evaluate_model(rf, X_val, y_val, model_name=f"RF Fold {k}")
        rf_metrics.append({
            "fold": k,
            "accuracy": rf_result["accuracy"],
            "f1_macro": rf_result["f1_macro"],
            "precision_macro": rf_result["precision_macro"],
            "recall_macro": rf_result["recall_macro"],
        })

        # XGBoost
        xgb, xgb_le = train_xgboost(X_train, y_train)
        xgb_result = evaluate_model(xgb, X_val, y_val, xgb_le, f"XGB Fold {k}")
        xgb_metrics.append({
            "fold": k,
            "accuracy": xgb_result["accuracy"],
            "f1_macro": xgb_result["f1_macro"],
            "precision_macro": xgb_result["precision_macro"],
            "recall_macro": xgb_result["recall_macro"],
        })

    # Log average metrics
    if rf_metrics:
        rf_acc = [m["accuracy"] for m in rf_metrics]
        rf_f1 = [m["f1_macro"] for m in rf_metrics]
        log.info("Walk-forward RF accuracy: %.3f ± %.3f, F1: %.3f ± %.3f",
                 np.mean(rf_acc), np.std(rf_acc), np.mean(rf_f1), np.std(rf_f1))
    if xgb_metrics:
        xgb_acc = [m["accuracy"] for m in xgb_metrics]
        xgb_f1 = [m["f1_macro"] for m in xgb_metrics]
        log.info("Walk-forward XGB accuracy: %.3f ± %.3f, F1: %.3f ± %.3f",
                 np.mean(xgb_acc), np.std(xgb_acc), np.mean(xgb_f1), np.std(xgb_f1))

    # Persist metrics to JSON
    import json
    metrics_path = MODELS_DIR / "accuracy_metrics.json"
    metrics_data = {
        "random_forest": rf_metrics,
        "xgboost": xgb_metrics,
        "rf_mean_accuracy": float(np.mean([m["accuracy"] for m in rf_metrics])) if rf_metrics else None,
        "rf_mean_f1": float(np.mean([m["f1_macro"] for m in rf_metrics])) if rf_metrics else None,
        "xgb_mean_accuracy": float(np.mean([m["accuracy"] for m in xgb_metrics])) if xgb_metrics else None,
        "xgb_mean_f1": float(np.mean([m["f1_macro"] for m in xgb_metrics])) if xgb_metrics else None,
    }
    metrics_path.write_text(json.dumps(metrics_data, indent=2))
    log.info("Metrics saved to %s", metrics_path)

    # Train final production models on ALL data
    log.info("Training final production models on all %d samples...", len(samples))
    X_all, y_all = get_xy(samples)

    rf_model = train_random_forest(X_all, y_all)
    get_feature_importance(rf_model, "Random Forest")

    xgb_model, xgb_le = train_xgboost(X_all, y_all)
    get_feature_importance(xgb_model, "XGBoost")

    save_models(rf_model, xgb_model, xgb_le)

    # Save predictions for the full grid (not just the last sliding window)
    log.info("Building full grid features for prediction CSV...")
    outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
    full_features = build_grid_features(outages)
    full_features = assign_risk_labels(full_features)
    has_data = full_features[FEATURE_COLS].sum(axis=1) > 0
    full_features = full_features[has_data]

    for name, model, le in [("RandomForest", rf_model, None), ("XGBoost", xgb_model, xgb_le)]:
        preds = predict_cells(model, full_features, le)
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

        # Only keep cells with actual outage data
        has_data = features[FEATURE_COLS].sum(axis=1) > 0
        features = features[has_data]

        for name, model, le in [("RandomForest", rf_model, None), ("XGBoost", xgb_model, xgb_le)]:
            preds = predict_cells(model, features, le)
            out_path = MODELS_DIR / f"predictions_{name.lower()}.csv"
            preds.to_csv(out_path, index=False)
            log.info("%s predictions saved to %s (%d cells)", name, out_path, len(preds))
        return

    # --- Train with sliding-window temporal approach ---
    _train_and_save()
    log.info("Done.")


if __name__ == "__main__":
    main()
