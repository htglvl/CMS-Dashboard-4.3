"""Test deeper model configurations."""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight

from advanced_charts.risk_model import build_training_samples, get_xy, RISK_LABELS

# Load data
data_file = PROJECT_ROOT / "data" / "df_cleaned.csv"
outages = pd.read_csv(data_file, parse_dates=["incident_date_time"], low_memory=False)
samples = build_training_samples(outages)

# Walk-forward setup
cutoff_dates = samples["cutoff_date"].sort_values().unique()
n_folds = 5
fold_edges = np.array_split(np.arange(len(cutoff_dates)), n_folds)
fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

# Use last fold for quick test
train_mask = samples["cutoff_date"] <= fold_cutoffs[3]
val_mask = (samples["cutoff_date"] > fold_cutoffs[3]) & (samples["cutoff_date"] <= fold_cutoffs[4])

X_train, y_train = get_xy(samples[train_mask])
X_val, y_val = get_xy(samples[val_mask])

print(f"Train: {len(X_train):,}, Val: {len(X_val):,}")

# Model configurations
configs = {
    "RF (original)": {
        "n_estimators": 200, "max_depth": 12, "min_samples_split": 5,
        "min_samples_leaf": 2, "class_weight": "balanced"
    },
    "RF (deeper)": {
        "n_estimators": 300, "max_depth": 20, "min_samples_split": 3,
        "min_samples_leaf": 1, "class_weight": "balanced"
    },
    "RF (very deep)": {
        "n_estimators": 500, "max_depth": 30, "min_samples_split": 2,
        "min_samples_leaf": 1, "class_weight": "balanced"
    },
    "RF (no limit)": {
        "n_estimators": 500, "max_depth": None, "min_samples_split": 2,
        "min_samples_leaf": 1, "class_weight": "balanced"
    },
}

print("\n" + "=" * 70)
print("RANDOM FOREST CONFIGURATIONS")
print("=" * 70)

for name, params in configs.items():
    model = RandomForestClassifier(**params, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    
    acc = accuracy_score(y_val, y_pred)
    f1 = f1_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    prec = precision_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    rec = recall_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    
    print(f"\n{name}:")
    print(f"  acc: {acc:.3f}  F1: {f1:.3f}  prec: {prec:.3f}  rec: {rec:.3f}")

# XGBoost configurations
le = LabelEncoder()
y_train_encoded = le.fit_transform(y_train)
y_val_encoded = le.transform(y_val)

classes = np.unique(y_train_encoded)
class_weights = compute_class_weight("balanced", classes=classes, y=y_train_encoded)
weight_map = dict(zip(classes, class_weights))
sample_weights = np.array([weight_map[y] for y in y_train_encoded])

xgb_configs = {
    "XGB (original)": {
        "n_estimators": 200, "max_depth": 6, "learning_rate": 0.1,
        "subsample": 0.8, "colsample_bytree": 0.8
    },
    "XGB (deeper)": {
        "n_estimators": 300, "max_depth": 10, "learning_rate": 0.05,
        "subsample": 0.8, "colsample_bytree": 0.8
    },
    "XGB (very deep)": {
        "n_estimators": 500, "max_depth": 15, "learning_rate": 0.03,
        "subsample": 0.7, "colsample_bytree": 0.7
    },
    "XGB (extreme)": {
        "n_estimators": 800, "max_depth": 20, "learning_rate": 0.01,
        "subsample": 0.7, "colsample_bytree": 0.7, "min_child_weight": 1,
        "gamma": 0.1, "reg_alpha": 0.1, "reg_lambda": 1.0
    },
}

print("\n" + "=" * 70)
print("XGBOOST CONFIGURATIONS")
print("=" * 70)

for name, params in xgb_configs.items():
    model = XGBClassifier(**params, random_state=42, eval_metric="mlogloss", n_jobs=-1)
    model.fit(X_train, y_train_encoded, sample_weight=sample_weights)
    y_pred = le.inverse_transform(model.predict(X_val))
    
    acc = accuracy_score(y_val, y_pred)
    f1 = f1_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    prec = precision_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    rec = recall_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
    
    print(f"\n{name}:")
    print(f"  acc: {acc:.3f}  F1: {f1:.3f}  prec: {prec:.3f}  rec: {rec:.3f}")
