"""
Training-scheme comparison experiment
=====================================
Question: does expanding-window training over-weight the old (denser-network)
era, hurting performance on recent data?

Three schemes trained on the SAME walk-forward split (train <= fold 3 end,
validate = last fold ~2021-2026), same model hyperparameters as production:

  A. Expanding window            — train on all cutoffs <= T   (current behaviour)
  B. Rolling 10 years            — train on cutoffs in [T-10y, T]
  C. Expanding + recency weights — w = 0.5^(delta_years / half_life), default 5y

Results are appended incrementally to models/scheme_comparison.json so partial
progress survives a crash.

Usage:
    python evaluate_training_schemes.py
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from xgboost import XGBClassifier

from advanced_charts.risk_model import (
    DATA_FILE,
    MODELS_DIR,
    RISK_LABELS,
    build_training_samples,
    get_xy,
)

RESULTS_PATH = MODELS_DIR / "scheme_comparison.json"
HALF_LIFE_YEARS = 5.0
ROLLING_YEARS = 10


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Models — hyperparameters identical to production risk_model.py
# ---------------------------------------------------------------------------

def fit_rf(X, y, extra_weight=None):
    """Random Forest; class_weight='balanced' built in, optional recency weights."""
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y, sample_weight=extra_weight)
    return model, None


def fit_xgb(X, y, extra_weight=None):
    """XGBoost with class balancing (+ optional recency weights)."""
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    classes = np.unique(y_enc)
    cw = dict(zip(classes, compute_class_weight("balanced", classes=classes, y=y_enc)))
    sw = np.array([cw[v] for v in y_enc], dtype=float)
    if extra_weight is not None:
        sw = sw * extra_weight
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
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X, y_enc, sample_weight=sw)
    return model, le


def evaluate(model, le, X_val, y_val, tag: str) -> dict:
    y_pred = le.inverse_transform(model.predict(X_val)) if le is not None else model.predict(X_val)
    f1m = f1_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    acc = accuracy_score(y_val, y_pred)
    rep = classification_report(y_val, y_pred, labels=RISK_LABELS,
                                target_names=RISK_LABELS, zero_division=0)
    cm = confusion_matrix(y_val, y_pred, labels=RISK_LABELS)
    log(f"{tag}: F1(macro)={f1m:.4f}  acc={acc:.4f}")
    log(f"{tag} per-class:\n{rep}")
    log(f"{tag} confusion matrix:\n{cm}")
    return {"f1_macro": float(f1m), "accuracy": float(acc)}


def save_results(data: dict) -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(data, indent=2))
    log(f"Saved -> {RESULTS_PATH}")


def main() -> None:
    t0 = time.time()

    # ------------------------------------------------------------------ data
    outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
    log(f"Loaded {len(outages):,} outage records ({time.time()-t0:.0f}s)")

    samples = build_training_samples(outages)
    if samples.empty:
        log("ERROR: no training samples generated")
        sys.exit(1)
    log(f"Built {len(samples):,} sliding-window samples ({time.time()-t0:.0f}s)")

    # ------------------------------------------- same folds as _train_and_save
    cutoff_dates = samples["cutoff_date"].sort_values().unique()
    fold_edges = np.array_split(np.arange(len(cutoff_dates)), 5)
    fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]
    T_train = fold_cutoffs[3]
    val_mask = (samples["cutoff_date"] > fold_cutoffs[3]) & \
               (samples["cutoff_date"] <= fold_cutoffs[4])

    train_all = samples[samples["cutoff_date"] <= T_train].copy()
    val_data = samples[val_mask].copy()
    del samples
    X_tr_all, y_tr_all = get_xy(train_all)
    X_val, y_val = get_xy(val_data)

    dist = val_data["risk_level"].value_counts(normalize=True).round(3).to_dict()
    log(f"Train cutoffs: {train_all['cutoff_date'].min()} .. {T_train} ({len(train_all):,} rows)")
    log(f"Val   cutoffs: {fold_cutoffs[3]} .. {fold_cutoffs[4]} ({len(val_data):,} rows)")
    log(f"Val class distribution: {dist}")

    # Recency weights on the full training set (aligned with train_all rows)
    delta_years = (T_train - train_all["cutoff_date"]).dt.total_seconds() / (365.25 * 24 * 3600)
    w_recency_all = np.power(0.5, delta_years / HALF_LIFE_YEARS)

    # Rolling-N-year subset (same date range -> slice of the recency weights)
    roll_mask = (train_all["cutoff_date"] >= T_train - pd.DateOffset(years=ROLLING_YEARS)).values
    X_roll = X_tr_all[roll_mask]
    y_roll = np.asarray(y_tr_all)[roll_mask]
    w_recency_roll = w_recency_all[roll_mask]

    results = {
        "description": "Scheme A/B/C comparison, validation = last walk-forward fold",
        "train_end": str(T_train),
        "val_start": str(fold_cutoffs[3]),
        "val_end": str(fold_cutoffs[4]),
        "n_train_full": int(len(train_all)),
        "n_train_rolling10y": int(roll_mask.sum()),
        "n_val": int(len(val_data)),
        "val_class_dist": {str(k): float(v) for k, v in dist.items()},
        "half_life_years": HALF_LIFE_YEARS,
        "rolling_years": ROLLING_YEARS,
        "arms": {},
    }
    save_results(results)

    # name -> (fit_fn, X_train, y_train, extra_sample_weights)
    plans = [
        ("A_expanding_rf",   fit_rf,  X_tr_all, np.asarray(y_tr_all), None),
        ("A_expanding_xgb",  fit_xgb, X_tr_all, np.asarray(y_tr_all), None),
        ("B_rolling10y_rf",  fit_rf,  X_roll,   y_roll,                None),
        ("B_rolling10y_xgb", fit_xgb, X_roll,   y_roll,                None),
        ("C_recency_rf",     fit_rf,  X_tr_all, np.asarray(y_tr_all), w_recency_all),
        ("C_recency_xgb",    fit_xgb, X_tr_all, np.asarray(y_tr_all), w_recency_all),
    ]

    for name, fn, Xtr, ytr, sw in plans:
        try:
            t_arm = time.time()
            model, le = fn(Xtr, ytr, extra_weight=sw)
            res = evaluate(model, le, X_val, y_val, name)
            res["seconds"] = round(time.time() - t_arm, 1)
            res["n_train_used"] = int(len(Xtr))
            del model
            results["arms"][name] = res
            save_results(results)
        except Exception as e:  # noqa: BLE001 — keep remaining arms alive
            log(f"{name}: ERROR — {e}")
            results["arms"][name] = {"error": str(e)}
            save_results(results)

    # ------------------------------------------------------------- summary
    log("=" * 70)
    log("SUMMARY (validation = last fold, ~2021-2026)")
    log(f"{'Arm':<22} {'F1(macro)':>10} {'Accuracy':>10} {'n_train':>12} {'secs':>7}")
    for name, r in results["arms"].items():
        if "f1_macro" in r:
            log(f"{name:<22} {r['f1_macro']:>10.4f} {r['accuracy']:>10.4f} "
                f"{r['n_train_used']:>12,} {r['seconds']:>7.0f}")
        else:
            log(f"{name:<22} {'ERROR':>10}")
    log(f"Total time: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
