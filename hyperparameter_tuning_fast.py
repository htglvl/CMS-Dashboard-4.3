"""Fast hyperparameter tuning for RF and XGBoost with progress bars."""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import time
from tqdm import tqdm
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import f1_score

from advanced_charts.risk_model import build_training_samples, get_xy

# Load data
data_file = PROJECT_ROOT / "data" / "df_cleaned.csv"
outages = pd.read_csv(data_file, parse_dates=["incident_date_time"])
samples = build_training_samples(outages)

# Use last fold
cutoff_dates = samples["cutoff_date"].sort_values().unique()
fold_edges = np.array_split(np.arange(len(cutoff_dates)), 5)
fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

train_mask = samples["cutoff_date"] <= fold_cutoffs[3]
val_mask = (samples["cutoff_date"] > fold_cutoffs[3]) & (samples["cutoff_date"] <= fold_cutoffs[4])

X_train, y_train = get_xy(samples[train_mask])
X_val, y_val = get_xy(samples[val_mask])

print(f"Train: {len(X_train):,}, Val: {len(X_val):,}")

# ============================================================================
# Random Forest
# ============================================================================
print("\n" + "=" * 60)
print("RANDOM FOREST HYPERPARAMETER TUNING")
print("=" * 60)

rf_param_grid = {
    "n_estimators": [100, 200, 300, 500],
    "max_depth": [8, 10, 12, 15, 20],
    "min_samples_split": [2, 3, 5, 10],
    "min_samples_leaf": [1, 2, 3],
    "max_features": ["sqrt", "log2"],
}

# Generate all combinations
from itertools import product
rf_combinations = list(product(*rf_param_grid.values()))
rf_param_names = list(rf_param_grid.keys())

print(f"Total RF combinations: {len(rf_combinations)}")

rf_results = []
start_time = time.time()

for i, combo in enumerate(tqdm(rf_combinations, desc="RF tuning", unit="combo")):
    params = dict(zip(rf_param_names, combo))
    
    # Cross-validation
    cv_scores = []
    skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    for train_idx, val_idx in skf.split(X_train, y_train):
        X_cv_train, y_cv_train = X_train[train_idx], y_train[train_idx]
        X_cv_val, y_cv_val = X_train[val_idx], y_train[val_idx]
        
        model = RandomForestClassifier(**params, class_weight="balanced", random_state=42, n_jobs=-1)
        model.fit(X_cv_train, y_cv_train)
        y_pred = model.predict(X_cv_val)
        cv_scores.append(f1_score(y_cv_val, y_pred, average="macro", zero_division=0))
    
    mean_f1 = np.mean(cv_scores)
    rf_results.append({**params, "f1_macro": mean_f1})
    
    # ETA calculation
    elapsed = time.time() - start_time
    avg_time = elapsed / (i + 1)
    remaining = avg_time * (len(rf_combinations) - i - 1)
    tqdm.write(f"  [{i+1}/{len(rf_combinations)}] {params} -> F1={mean_f1:.4f} (ETA: {remaining/60:.1f}min)")

# Find best
rf_best = max(rf_results, key=lambda x: x["f1_macro"])
print(f"\nBest RF: {rf_best}")

# Evaluate on validation set
rf_model = RandomForestClassifier(
    n_estimators=rf_best["n_estimators"],
    max_depth=rf_best["max_depth"],
    min_samples_split=rf_best["min_samples_split"],
    min_samples_leaf=rf_best["min_samples_leaf"],
    class_weight="balanced", random_state=42, n_jobs=-1
)
rf_model.fit(X_train, y_train)
y_pred = rf_model.predict(X_val)
rf_val_f1 = f1_score(y_val, y_pred, average="macro", zero_division=0)
print(f"RF Validation F1(macro): {rf_val_f1:.4f}")

# ============================================================================
# XGBoost
# ============================================================================
print("\n" + "=" * 60)
print("XGBOOST HYPERPARAMETER TUNING")
print("=" * 60)

le = LabelEncoder()
y_train_encoded = le.fit_transform(y_train)
y_val_encoded = le.transform(y_val)

classes = np.unique(y_train_encoded)
class_weights = compute_class_weight("balanced", classes=classes, y=y_train_encoded)
weight_map = dict(zip(classes, class_weights))
sample_weights = np.array([weight_map[y] for y in y_train_encoded])

xgb_param_grid = {
    "n_estimators": [200, 300, 500],
    "max_depth": [4, 6, 8, 10],
    "learning_rate": [0.01, 0.03, 0.05, 0.1],
    "subsample": [0.6, 0.7, 0.8],
    "colsample_bytree": [0.6, 0.7, 0.8],
    "min_child_weight": [1, 3, 5],
    "gamma": [0, 0.1, 0.2],
}

xgb_combinations = list(product(*xgb_param_grid.values()))
xgb_param_names = list(xgb_param_grid.keys())

print(f"Total XGB combinations: {len(xgb_combinations)}")

xgb_results = []
start_time = time.time()

for i, combo in enumerate(tqdm(xgb_combinations, desc="XGB tuning", unit="combo")):
    params = dict(zip(xgb_param_names, combo))
    
    cv_scores = []
    skf = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
    for train_idx, val_idx in skf.split(X_train, y_train_encoded):
        X_cv_train = X_train[train_idx]
        y_cv_train = y_train_encoded[train_idx]
        X_cv_val = X_train[val_idx]
        y_cv_val = y_train_encoded[val_idx]
        
        weights = np.array([weight_map[y] for y in y_cv_train])
        
        model = XGBClassifier(**params, reg_alpha=0.1, reg_lambda=1.0,
                             random_state=42, eval_metric="mlogloss", n_jobs=-1)
        model.fit(X_cv_train, y_cv_train, sample_weight=weights)
        y_pred = le.inverse_transform(model.predict(X_cv_val))
        y_cv_val_orig = le.inverse_transform(y_cv_val)
        cv_scores.append(f1_score(y_cv_val_orig, y_pred, average="macro", zero_division=0))
    
    mean_f1 = np.mean(cv_scores)
    xgb_results.append({**params, "f1_macro": mean_f1})
    
    elapsed = time.time() - start_time
    avg_time = elapsed / (i + 1)
    remaining = avg_time * (len(xgb_combinations) - i - 1)
    tqdm.write(f"  [{i+1}/{len(xgb_combinations)}] {params} -> F1={mean_f1:.4f} (ETA: {remaining/60:.1f}min)")

# Find best
xgb_best = max(xgb_results, key=lambda x: x["f1_macro"])
print(f"\nBest XGB: {xgb_best}")

# Evaluate on validation set
xgb_model = XGBClassifier(
    n_estimators=xgb_best["n_estimators"],
    max_depth=xgb_best["max_depth"],
    learning_rate=xgb_best["learning_rate"],
    subsample=xgb_best["subsample"],
    colsample_bytree=xgb_best["colsample_bytree"],
    min_child_weight=1, gamma=0.1, reg_alpha=0.1, reg_lambda=1.0,
    random_state=42, eval_metric="mlogloss", n_jobs=-1
)
xgb_model.fit(X_train, y_train_encoded, sample_weight=sample_weights)
y_pred = le.inverse_transform(xgb_model.predict(X_val))
xgb_val_f1 = f1_score(y_val, y_pred, average="macro", zero_division=0)
print(f"XGB Validation F1(macro): {xgb_val_f1:.4f}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"RF best:  {rf_best} -> Val F1={rf_val_f1:.4f}")
print(f"XGB best: {xgb_best} -> Val F1={xgb_val_f1:.4f}")
