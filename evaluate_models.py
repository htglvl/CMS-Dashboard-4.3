"""
Enhanced Model Evaluation Script
=================================
Compares multiple model configurations to find the best F1 score.

Configurations tested:
1. Original baseline (before improvements)
2. Improved RF/XGB (current hyperparameters)
3. SMOTE oversampling
4. SMOTE + deeper trees
5. Threshold tuning

Usage:
    python evaluate_models.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import json
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    classification_report,
    confusion_matrix,
)
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_class_weight

from advanced_charts.risk_model import (
    build_training_samples,
    get_xy,
    FEATURE_COLS,
    RISK_LABELS,
    MODELS_DIR,
)


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def make_rf_original(X_train, y_train):
    """Original RF (before improvements)."""
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model, None


def make_rf_improved(X_train, y_train):
    """Improved RF (current)."""
    model = RandomForestClassifier(
        n_estimators=500,
        max_depth=15,
        min_samples_split=3,
        min_samples_leaf=1,
        max_features="sqrt",
        class_weight="balanced_subsample",
        bootstrap=True,
        oob_score=True,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model, None


def make_rf_deep(X_train, y_train):
    """Deeper RF with more trees."""
    model = RandomForestClassifier(
        n_estimators=800,
        max_depth=25,
        min_samples_split=2,
        min_samples_leaf=1,
        max_features="sqrt",
        class_weight="balanced_subsample",
        bootstrap=True,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model, None


def make_xgb_original(X_train, y_train):
    """Original XGB (before improvements, no class balancing)."""
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_train)
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_train, y_encoded)
    return model, le


def make_xgb_improved(X_train, y_train):
    """Improved XGB with class balancing."""
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_train)
    classes = np.unique(y_encoded)
    class_weights = compute_class_weight("balanced", classes=classes, y=y_encoded)
    weight_map = dict(zip(classes, class_weights))
    sample_weights = np.array([weight_map[y] for y in y_encoded])
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_train, y_encoded, sample_weight=sample_weights)
    return model, le


def make_xgb_deep(X_train, y_train):
    """Deeper XGB with stronger class balancing."""
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_train)
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
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_train, y_encoded, sample_weight=sample_weights)
    return model, le


def make_rf_smote(X_train, y_train):
    """RF with SMOTE oversampling."""
    from imblearn.over_sampling import SMOTE
    smote = SMOTE(random_state=42, k_neighbors=3)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    model = RandomForestClassifier(
        n_estimators=500,
        max_depth=15,
        min_samples_split=3,
        min_samples_leaf=1,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_res, y_res)
    return model, None


def make_xgb_smote(X_train, y_train):
    """XGB with SMOTE oversampling."""
    from imblearn.over_sampling import SMOTE
    smote = SMOTE(random_state=42, k_neighbors=3)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_res)
    model = XGBClassifier(
        n_estimators=300,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=1,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_res, y_encoded)
    return model, le


def make_rf_smote_deep(X_train, y_train):
    """RF with SMOTE + deeper trees."""
    from imblearn.over_sampling import SMOTE
    smote = SMOTE(random_state=42, k_neighbors=3)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    model = RandomForestClassifier(
        n_estimators=800,
        max_depth=30,
        min_samples_split=2,
        min_samples_leaf=1,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_res, y_res)
    return model, None


def make_xgb_smote_deep(X_train, y_train):
    """XGB with SMOTE + deeper trees."""
    from imblearn.over_sampling import SMOTE
    smote = SMOTE(random_state=42, k_neighbors=3)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_res)
    model = XGBClassifier(
        n_estimators=500,
        max_depth=12,
        learning_rate=0.03,
        subsample=0.7,
        colsample_bytree=0.7,
        min_child_weight=1,
        gamma=0.1,
        random_state=42,
        use_label_encoder=False,
        eval_metric="mlogloss",
        n_jobs=-1,
    )
    model.fit(X_res, y_encoded)
    return model, le


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate_model(model, X_test, y_test, label_encoder=None):
    """Compute all metrics."""
    if label_encoder is not None:
        y_pred = label_encoder.inverse_transform(model.predict(X_test))
        y_proba = model.predict_proba(X_test)
    else:
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "f1_macro": f1_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0),
        "f1_weighted": f1_score(y_test, y_pred, labels=RISK_LABELS, average="weighted", zero_division=0),
        "precision_macro": precision_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0),
        "recall_macro": recall_score(y_test, y_pred, labels=RISK_LABELS, average="macro", zero_division=0),
        "y_pred": y_pred,
        "y_proba": y_proba,
    }


def threshold_tune(model, X_val, y_val, label_encoder=None):
    """Tune classification thresholds to maximise macro F1."""
    if label_encoder is not None:
        y_proba = model.predict_proba(X_val)
        classes = label_encoder.classes_
    else:
        y_proba = model.predict_proba(X_val)
        classes = model.classes_

    best_f1 = 0
    best_thresholds = {c: 0.5 for c in classes}

    # Simple grid search over thresholds for each class
    from itertools import product
    thresholds = [0.2, 0.3, 0.4, 0.5]

    for combo in product(thresholds, repeat=len(classes)):
        thresholds_map = dict(zip(classes, combo))
        y_pred = []
        for proba in y_proba:
            # Assign class with highest (probability / threshold)
            scores = {classes[i]: proba[i] / thresholds_map[classes[i]] for i in range(len(classes))}
            y_pred.append(max(scores, key=scores.get))

        f1 = f1_score(y_val, y_pred, labels=RISK_LABELS, average="macro", zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_thresholds = thresholds_map

    return best_f1, best_thresholds


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

CONFIGS = {
    # Original baselines
    "RF (original)": make_rf_original,
    "XGB (original)": make_xgb_original,
    # Improved
    "RF (improved)": make_rf_improved,
    "XGB (improved)": make_xgb_improved,
    # Deeper
    "RF (deep)": make_rf_deep,
    "XGB (deep)": make_xgb_deep,
    # SMOTE
    "RF + SMOTE": make_rf_smote,
    "XGB + SMOTE": make_xgb_smote,
    # SMOTE + deep
    "RF + SMOTE + deep": make_rf_smote_deep,
    "XGB + SMOTE + deep": make_xgb_smote_deep,
}


def run_evaluation():
    """Run walk-forward evaluation across all configurations."""
    print("=" * 80)
    print("  MODEL EVALUATION — All Configurations")
    print("=" * 80)

    data_file = PROJECT_ROOT / "data" / "df_cleaned.csv"
    if not data_file.exists():
        print(f"ERROR: Data file not found: {data_file}")
        return

    outages = pd.read_csv(data_file, parse_dates=["incident_date_time"])
    print(f"\nLoaded {len(outages):,} outage records")

    samples = build_training_samples(outages)
    if samples.empty:
        print("ERROR: No training samples generated")
        return

    print(f"Generated {len(samples):,} training samples")

    # Walk-forward folds
    cutoff_dates = samples["cutoff_date"].sort_values().unique()
    n_folds = 5
    fold_edges = np.array_split(np.arange(len(cutoff_dates)), n_folds)
    fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]

    print(f"Walk-forward: {n_folds} folds")
    print("-" * 80)

    # Store results per config
    all_results = {name: [] for name in CONFIGS}

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

        print(f"\nFold {k}: train={len(train_data):,}, val={len(val_data):,}")

        for name, factory in CONFIGS.items():
            try:
                model, le = factory(X_train, y_train)
                result = evaluate_model(model, X_val, y_val, le)
                all_results[name].append({
                    "fold": k,
                    "accuracy": result["accuracy"],
                    "f1_macro": result["f1_macro"],
                    "f1_weighted": result["f1_weighted"],
                    "precision_macro": result["precision_macro"],
                    "recall_macro": result["recall_macro"],
                })
            except Exception as e:
                print(f"  {name}: ERROR — {e}")

    # Summary table
    print("\n" + "=" * 80)
    print("  COMPARISON SUMMARY (mean ± std across folds)")
    print("=" * 80)

    def mean_std(results, key):
        vals = [r[key] for r in results]
        return np.mean(vals), np.std(vals)

    summary_rows = []
    for name, results in all_results.items():
        if not results:
            continue
        row = {"config": name}
        for metric in ["accuracy", "f1_macro", "f1_weighted", "precision_macro", "recall_macro"]:
            m, s = mean_std(results, metric)
            row[f"{metric}_mean"] = float(m)
            row[f"{metric}_std"] = float(s)
        summary_rows.append(row)

    # Sort by F1 macro
    summary_rows.sort(key=lambda r: r["f1_macro_mean"], reverse=True)

    print(f"\n{'Config':<25} {'Accuracy':>14} {'F1(macro)':>14} {'F1(weighted)':>14} {'Precision':>14} {'Recall':>14}")
    print("-" * 95)
    for row in summary_rows:
        print(f"{row['config']:<25} "
              f"{row['accuracy_mean']:.3f}±{row['accuracy_std']:.3f}  "
              f"{row['f1_macro_mean']:.3f}±{row['f1_macro_std']:.3f}  "
              f"{row['f1_weighted_mean']:.3f}±{row['f1_weighted_std']:.3f}  "
              f"{row['precision_macro_mean']:.3f}±{row['precision_macro_std']:.3f}  "
              f"{row['recall_macro_mean']:.3f}±{row['recall_macro_std']:.3f}")

    # Best config
    best = summary_rows[0]
    print(f"\n{'=' * 80}")
    print(f"  BEST CONFIG: {best['config']}")
    print(f"  F1(macro): {best['f1_macro_mean']:.3f} ± {best['f1_macro_std']:.3f}")
    print(f"  Accuracy:  {best['accuracy_mean']:.3f} ± {best['accuracy_std']:.3f}")
    print(f"{'=' * 80}")

    # Threshold tuning on best config's last fold
    print("\n  Running threshold tuning on best config (last fold)...")
    last_k = n_folds - 1
    train_mask = samples["cutoff_date"] <= fold_cutoffs[last_k - 1]
    val_mask = (samples["cutoff_date"] > fold_cutoffs[last_k - 1]) & \
               (samples["cutoff_date"] <= fold_cutoffs[last_k])

    if not samples[train_mask].empty and not samples[val_mask].empty:
        X_train, y_train = get_xy(samples[train_mask])
        X_val, y_val = get_xy(samples[val_mask])

        best_factory = CONFIGS[best["config"]]
        model, le = best_factory(X_train, y_train)
        base_result = evaluate_model(model, X_val, y_val, le)

        tuned_f1, tuned_thresholds = threshold_tune(model, X_val, y_val, le)
        print(f"  Base F1(macro):    {base_result['f1_macro']:.3f}")
        print(f"  Tuned F1(macro):   {tuned_f1:.3f}")
        print(f"  Tuned thresholds:  {tuned_thresholds}")

        # Detailed report for best config
        print(f"\n{'=' * 80}")
        print(f"  DETAILED REPORT — {best['config']} (last fold)")
        print(f"{'=' * 80}")
        y_pred = base_result["y_pred"]
        print(classification_report(y_val, y_pred, labels=RISK_LABELS, target_names=RISK_LABELS, zero_division=0))

        cm = confusion_matrix(y_val, y_pred, labels=RISK_LABELS)
        print("Confusion Matrix:")
        print(f"         {'  '.join(f'{l:>8}' for l in RISK_LABELS)}")
        for i, label in enumerate(RISK_LABELS):
            print(f"  {label:<8} {'  '.join(f'{v:>8}' for v in cm[i])}")

    # Save results
    output = {
        "summary": summary_rows,
        "best_config": best["config"],
        "best_f1_macro": best["f1_macro_mean"],
    }
    output_path = MODELS_DIR / "evaluation_results.json"
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {output_path}")

    return output


if __name__ == "__main__":
    run_evaluation()
