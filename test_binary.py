"""Test binary classification (risk vs no-risk) for better performance."""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score, classification_report
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight

from advanced_charts.risk_model import build_training_samples, get_xy, FEATURE_COLS

# Load data
data_file = PROJECT_ROOT / "data" / "df_cleaned.csv"
outages = pd.read_csv(data_file, parse_dates=["incident_date_time"], low_memory=False)
samples = build_training_samples(outages)

# Convert to binary: Low=0, Medium+High=1
samples["binary_risk"] = (samples["risk_level"] != "Low").astype(int)

print("Binary class distribution:")
for label, count in samples["binary_risk"].value_counts().items():
    name = "No Risk" if label == 0 else "Risk"
    print(f"  {name}: {count:,} ({count/len(samples)*100:.1f}%)")

# Walk-forward validation
cutoff_dates = samples["cutoff_date"].sort_values().unique()
n_folds = 5
fold_edges = np.array_split(np.arange(len(cutoff_dates)), n_folds)
fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

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

    X_train = train_data[FEATURE_COLS].values
    y_train = train_data["binary_risk"].values
    X_val = val_data[FEATURE_COLS].values
    y_val = val_data["binary_risk"].values

    # RF
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=12, min_samples_split=5,
        min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1
    )
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_val)
    rf_metrics.append({
        "accuracy": accuracy_score(y_val, rf_pred),
        "f1": f1_score(y_val, rf_pred, average="binary"),
        "precision": precision_score(y_val, rf_pred, average="binary"),
        "recall": recall_score(y_val, rf_pred, average="binary"),
    })

    # XGB
    le = LabelEncoder()
    y_train_encoded = le.fit_transform(y_train)
    classes = np.unique(y_train_encoded)
    class_weights = compute_class_weight("balanced", classes=classes, y=y_train_encoded)
    weight_map = dict(zip(classes, class_weights))
    sample_weights = np.array([weight_map[y] for y in y_train_encoded])

    xgb = XGBClassifier(
        n_estimators=300, max_depth=10, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7, min_child_weight=1,
        gamma=0.2, reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, eval_metric="mlogloss", n_jobs=-1
    )
    xgb.fit(X_train, y_train_encoded, sample_weight=sample_weights)
    xgb_pred = le.inverse_transform(xgb.predict(X_val))
    xgb_metrics.append({
        "accuracy": accuracy_score(y_val, xgb_pred),
        "f1": f1_score(y_val, xgb_pred, average="binary"),
        "precision": precision_score(y_val, xgb_pred, average="binary"),
        "recall": recall_score(y_val, xgb_pred, average="binary"),
    })

# Summary
print("\n" + "=" * 70)
print("BINARY CLASSIFICATION RESULTS")
print("=" * 70)

def mean_std(metrics, key):
    vals = [m[key] for m in metrics]
    return np.mean(vals), np.std(vals)

for model_name, metrics in [("Random Forest", rf_metrics), ("XGBoost", xgb_metrics)]:
    print(f"\n{model_name}:")
    for key in ["accuracy", "f1", "precision", "recall"]:
        m, s = mean_std(metrics, key)
        print(f"  {key}: {m:.3f} +/- {s:.3f}")

# Last fold detailed
print("\n" + "=" * 70)
print("LAST FOLD — DETAILED")
print("=" * 70)

last_k = n_folds - 1
train_mask = samples["cutoff_date"] <= fold_cutoffs[last_k - 1]
val_mask = (samples["cutoff_date"] > fold_cutoffs[last_k - 1]) & \
           (samples["cutoff_date"] <= fold_cutoffs[last_k])

X_train = samples[train_mask][FEATURE_COLS].values
y_train = samples[train_mask]["binary_risk"].values
X_val = samples[val_mask][FEATURE_COLS].values
y_val = samples[val_mask]["binary_risk"].values

rf = RandomForestClassifier(
    n_estimators=200, max_depth=12, min_samples_split=5,
    min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1
)
rf.fit(X_train, y_train)
rf_pred = rf.predict(X_val)

print("\nRandom Forest:")
print(classification_report(y_val, rf_pred, target_names=["No Risk", "Risk"]))

# Compare: what % of actual High-risk cells does the model catch?
val_data = samples[val_mask]
high_risk_mask = val_data["risk_level"] == "High"
high_risk_predicted = rf_pred[high_risk_mask]
high_risk_caught = (high_risk_predicted == 1).sum()
high_risk_total = high_risk_mask.sum()
print(f"\nHigh-risk cells caught: {high_risk_caught}/{high_risk_total} ({high_risk_caught/high_risk_total*100:.1f}%)")
