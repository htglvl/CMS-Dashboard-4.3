"""Verify model performance for the actual models used in the website.
Run: python verify_model_results.py
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score, precision_score, recall_score

from advanced_charts.risk_model import (
    build_training_samples, get_xy, train_random_forest, train_xgboost,
    RISK_LABELS, MODELS_DIR
)

# Load data
data_file = PROJECT_ROOT / "data" / "df_cleaned.csv"
outages = pd.read_csv(data_file, parse_dates=["incident_date_time"])
samples = build_training_samples(outages)

print(f"Total samples: {len(samples):,}")
print(f"Class distribution:")
for label, count in samples["risk_level"].value_counts().items():
    print(f"  {label}: {count:,} ({count/len(samples)*100:.1f}%)")

# Walk-forward validation (same as website)
cutoff_dates = samples["cutoff_date"].sort_values().unique()
n_folds = 5
fold_edges = np.array_split(np.arange(len(cutoff_dates)), n_folds)
fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

rf_metrics = []
xgb_metrics = []

print("\n" + "=" * 70)
print("WALK-FORWARD VALIDATION")
print("=" * 70)

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

    # RF
    rf = train_random_forest(X_train, y_train)
    rf_pred = rf.predict(X_val)
    rf_acc = accuracy_score(y_val, rf_pred)
    rf_f1 = f1_score(y_val, rf_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    rf_prec = precision_score(y_val, rf_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    rf_rec = recall_score(y_val, rf_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    rf_metrics.append({"accuracy": rf_acc, "f1_macro": rf_f1, "precision": rf_prec, "recall": rf_rec})

    # XGB
    xgb, xgb_le = train_xgboost(X_train, y_train)
    xgb_pred = xgb_le.inverse_transform(xgb.predict(X_val))
    xgb_acc = accuracy_score(y_val, xgb_pred)
    xgb_f1 = f1_score(y_val, xgb_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    xgb_prec = precision_score(y_val, xgb_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    xgb_rec = recall_score(y_val, xgb_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    xgb_metrics.append({"accuracy": xgb_acc, "f1_macro": xgb_f1, "precision": xgb_prec, "recall": xgb_rec})

    print(f"\nFold {k}: train={len(train_data):,}, val={len(val_data):,}")
    print(f"  RF  — acc: {rf_acc:.3f}  F1: {rf_f1:.3f}  prec: {rf_prec:.3f}  rec: {rf_rec:.3f}")
    print(f"  XGB — acc: {xgb_acc:.3f}  F1: {xgb_f1:.3f}  prec: {xgb_prec:.3f}  rec: {xgb_rec:.3f}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

def mean_std(metrics, key):
    vals = [m[key] for m in metrics]
    return np.mean(vals), np.std(vals)

for model_name, metrics in [("Random Forest", rf_metrics), ("XGBoost", xgb_metrics)]:
    print(f"\n{model_name}:")
    for key in ["accuracy", "f1_macro", "precision", "recall"]:
        m, s = mean_std(metrics, key)
        print(f"  {key}: {m:.3f} ± {s:.3f}")

# Last fold detailed report
print("\n" + "=" * 70)
print("LAST FOLD — DETAILED REPORT")
print("=" * 70)

# Re-run last fold
last_k = n_folds - 1
train_mask = samples["cutoff_date"] <= fold_cutoffs[last_k - 1]
val_mask = (samples["cutoff_date"] > fold_cutoffs[last_k - 1]) & \
           (samples["cutoff_date"] <= fold_cutoffs[last_k])

X_train, y_train = get_xy(samples[train_mask])
X_val, y_val = get_xy(samples[val_mask])

rf = train_random_forest(X_train, y_train)
rf_pred = rf.predict(X_val)

xgb, xgb_le = train_xgboost(X_train, y_train)
xgb_pred = xgb_le.inverse_transform(xgb.predict(X_val))

print("\n--- Random Forest ---")
print(classification_report(y_val, rf_pred, labels=RISK_LABELS, target_names=RISK_LABELS, zero_division=0))
print("Confusion Matrix:")
cm_rf = confusion_matrix(y_val, rf_pred, labels=RISK_LABELS)
print(f"         {'  '.join(f'{l:>8}' for l in RISK_LABELS)}")
for i, label in enumerate(RISK_LABELS):
    print(f"  {label:<8} {'  '.join(f'{v:>8}' for v in cm_rf[i])}")

print("\n--- XGBoost ---")
print(classification_report(y_val, xgb_pred, labels=RISK_LABELS, target_names=RISK_LABELS, zero_division=0))
print("Confusion Matrix:")
cm_xgb = confusion_matrix(y_val, xgb_pred, labels=RISK_LABELS)
print(f"         {'  '.join(f'{l:>8}' for l in RISK_LABELS)}")
for i, label in enumerate(RISK_LABELS):
    print(f"  {label:<8} {'  '.join(f'{v:>8}' for v in cm_xgb[i])}")
