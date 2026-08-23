"""
Purge / leakage quantification experiment
=========================================
Follow-up to evaluate_training_schemes.py. Tests the hypothesis that
"the model memorised training data and the val set is largely leaked",
which would mean walk-forward metrics are inflated by window overlap.

Design (validation fixed: last fold 2021-04 .. 2026-05):

  Arms (RF + XGB, production hyperparameters):
    nopurge — train cutoffs <= T                (current behaviour, T = 2021-04)
    purge15 — train cutoffs <= T - 15 months    (removes ALL feature/label
                                                 overlap: last train label
                                                 window ends 2020-04, earliest
                                                 val feature window starts 2020-05)

  Diagnostics per arm:
    - F1(macro) on FULL val
    - F1(macro) on NEAR-val  (cutoff <= T + 15m = 2022-07; only region where
                              train-label -> val-feature overlap is possible)
    - F1(macro) on FAR-val   (cutoff > 2022-07; provably overlap-free)
    - F1(macro) on a 200k subsample of the arm's OWN training rows
      (memorisation gauge: big gap vs val => strong fitting of train noise)

Usage:
    python evaluate_purge_effect.py
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

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from advanced_charts.risk_model import (
    DATA_FILE,
    MODELS_DIR,
    RISK_LABELS,
    build_training_samples,
    get_xy,
)

RESULTS_PATH = MODELS_DIR / "purge_experiment.json"
SAMPLES_CACHE = PROJECT_ROOT / "data" / "sliding_samples_cache.pkl"
TRAIN_SUBSAMPLE = 200_000

# reuse identical fit functions / logging from the scheme experiment
from evaluate_training_schemes import fit_rf, fit_xgb, log


def save_results(data: dict) -> None:
    MODELS_DIR.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(data, indent=2))
    log(f"Saved -> {RESULTS_PATH}")


def main() -> None:
    t0 = time.time()

    # ------------------------------------------------------------- samples
    if SAMPLES_CACHE.exists():
        samples = joblib.load(SAMPLES_CACHE)
        log(f"Loaded {len(samples):,} samples from cache ({time.time()-t0:.0f}s)")
    else:
        outages = pd.read_csv(DATA_FILE, parse_dates=["incident_date_time"])
        log(f"Loaded {len(outages):,} outage records ({time.time()-t0:.0f}s)")
        samples = build_training_samples(outages)
        joblib.dump(samples, SAMPLES_CACHE)
        log(f"Built + cached {len(samples):,} samples ({time.time()-t0:.0f}s)")

    # --------------------------------------------------------------- split
    cutoff_dates = samples["cutoff_date"].sort_values().unique()
    fold_edges = np.array_split(np.arange(len(cutoff_dates)), 5)
    fold_cutoffs = [cutoff_dates[edges[-1]] for edges in fold_edges]
    T_train = fold_cutoffs[3]
    PURGE = pd.DateOffset(months=15)
    purge_end = T_train - PURGE          # last allowed train cutoff under purge
    leak_horizon = T_train + PURGE       # val cutoffs beyond this are overlap-free

    val = samples[(samples["cutoff_date"] > T_train) &
                  (samples["cutoff_date"] <= fold_cutoffs[4])].copy()
    near_mask = (val["cutoff_date"] <= leak_horizon).values
    X_val, y_val = get_xy(val)
    y_val = np.asarray(y_val)
    X_near, y_near = X_val[near_mask], y_val[near_mask]
    X_far, y_far = X_val[~near_mask], y_val[~near_mask]

    log(f"T_train={T_train.date()}  purge_end={purge_end.date()}  "
        f"leak_horizon={leak_horizon.date()}")
    log(f"Val: {len(val):,} rows | NEAR (possible leak): {near_mask.sum():,} "
        f"| FAR (overlap-free): {(~near_mask).sum():,}")

    tr_nopurge = samples[samples["cutoff_date"] <= T_train]
    tr_purge = samples[samples["cutoff_date"] <= purge_end]

    results = {
        "description": "Purge effect + memorisation gauge, val = last fold",
        "t_train": str(T_train),
        "purge_end": str(purge_end),
        "leak_horizon": str(leak_horizon),
        "n_val": int(len(val)),
        "n_near": int(near_mask.sum()),
        "n_far": int((~near_mask).sum()),
        "arms": {},
    }
    save_results(results)

    plans = [
        ("rf_nopurge", fit_rf, tr_nopurge),
        ("xgb_nopurge", fit_xgb, tr_nopurge),
        ("rf_purge15", fit_rf, tr_purge),
        ("xgb_purge15", fit_xgb, tr_purge),
    ]

    for name, fn, tr_data in plans:
        try:
            t_arm = time.time()
            Xtr, ytr = get_xy(tr_data)
            ytr_arr = np.asarray(ytr)
            model, le = fn(Xtr, ytr_arr)

            def pred(X):
                p = model.predict(X)
                return le.inverse_transform(p) if le is not None else p

            # val diagnostics
            y_pv = pred(X_val)
            f1_all = f1_score(y_val, y_pv, labels=RISK_LABELS, average="macro", zero_division=0)
            f1_near = f1_score(y_near, y_pv[near_mask], labels=RISK_LABELS,
                               average="macro", zero_division=0)
            f1_far = f1_score(y_far, y_pv[~near_mask], labels=RISK_LABELS,
                              average="macro", zero_division=0)
            acc_all = accuracy_score(y_val, y_pv)

            # memorisation gauge: score a subsample of the arm's own training rows
            rng = np.random.default_rng(42)
            idx = rng.choice(len(Xtr), size=min(TRAIN_SUBSAMPLE, len(Xtr)), replace=False)
            y_ptr = pred(Xtr[idx])
            f1_train_sub = f1_score(ytr_arr[idx], y_ptr, labels=RISK_LABELS,
                                    average="macro", zero_division=0)

            cm_far = confusion_matrix(y_far, y_pv[~near_mask], labels=RISK_LABELS)

            res = {
                "f1_val_full": float(f1_all),
                "f1_val_near_possible_leak": float(f1_near),
                "f1_val_far_overlap_free": float(f1_far),
                "f1_train_subsample_200k": float(f1_train_sub),
                "accuracy_val_full": float(acc_all),
                "n_train_used": int(len(Xtr)),
                "seconds": round(time.time() - t_arm, 1),
            }
            log(f"{name}: F1 val={f1_all:.4f} | near={f1_near:.4f} | far={f1_far:.4f} "
                f"| train_sub={f1_train_sub:.4f}")
            log(f"{name} confusion matrix (FAR, overlap-free):\n{cm_far}")

            del model
            results["arms"][name] = res
            save_results(results)
        except Exception as e:  # noqa: BLE001
            log(f"{name}: ERROR — {e}")
            results["arms"][name] = {"error": str(e)}
            save_results(results)

    # ------------------------------------------------------------- summary
    log("=" * 78)
    log("SUMMARY")
    log(f"{'Arm':<14} {'F1 val':>8} {'F1 near(leak?)':>15} {'F1 far(clean)':>14} "
        f"{'F1 train_sub':>13} {'gap':>7}")
    for name, r in results["arms"].items():
        if "f1_val_full" in r:
            gap = r["f1_train_subsample_200k"] - r["f1_val_full"]
            log(f"{name:<14} {r['f1_val_full']:>8.4f} "
                f"{r['f1_val_near_possible_leak']:>15.4f} "
                f"{r['f1_val_far_overlap_free']:>14.4f} "
                f"{r['f1_train_subsample_200k']:>13.4f} {gap:>7.4f}")
        else:
            log(f"{name:<14} ERROR")
    log(f"Total time: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
