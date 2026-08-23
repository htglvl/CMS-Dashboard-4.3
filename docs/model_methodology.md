# Risk Model Methodology

How the outage risk model (High / Medium / Low per grid cell) is trained,
validated, and deployed — and, importantly, **why** each choice was made.
Empirical claims below are backed by reproducible experiments
(`evaluate_training_schemes.py`, `evaluate_purge_effect.py`); results in
`models/scheme_comparison.json` and `models/purge_experiment.json`.

---

## 1. Task definition

> Predict, for every ~2 km grid cell, the risk that it experiences outages
> over the **next 3 months**, using only information available at prediction
> time (the preceding 12 months of outage history).

- One training sample = *(grid cell × monthly cutoff date)*.
- Features aggregate the **12 months before** the cutoff; labels count
  outages in the **3 months after** it. Feature and label windows never
  overlap by construction.

## 2. Label definition — frozen threshold (not per-window quantiles)

```
Low    = 0 outages in the next 3 months
Medium = 1 … T   outages
High   = > T     outages,  where T = 67th percentile of NON-ZERO future
                            counts in the TRAINING pool only
```

**Why not quantiles computed per window?** Originally each monthly window
binned counts at its own 67th percentile. That makes "High" a *moving
target*: the same cell with 5 upcoming outages could be Medium in one month
and High the next depending on that window's distribution — a non-stationary
label the model cannot learn, and one whose definition silently depends on
future data. Freezing `T` on training data gives every window (train,
validation, production) one consistent meaning; per-fold freezing keeps it
strictly leak-free during validation. The value is recorded per fold in
`accuracy_metrics.json → fold_thresholds`, and the production value in
`production_high_threshold`.

The static map colouring (`assign_risk_labels`) accepts the same frozen
threshold so dashboard semantics match training semantics.

## 3. Train/validation split — purged expanding-window walk-forward

Five chronological folds over ~290 monthly cutoffs (≈5 years per fold).
For fold *k*:

```
train : cutoff ≤ fold_boundary(k) − 15 months        ← PURGE gap
val   : fold_boundary(k−1) < cutoff ≤ fold_boundary(k)
```

**Why chronological?** Samples share space and time; a random split would
place neighbouring cells/months on both sides of the split and report
near-duplicate accuracy (classic leakage for spatio-temporal data).
Walk-forward always validates on the *future*, matching deployment reality.

**Why the 15-month purge?** A training sample's label window `[C, C+3mo)`
can overlap a validation sample's feature window `[V−12mo, V)` whenever
`V < C + 15`. Without a gap, outages counted in late-training *answers*
reappear inside early-validation *inputs*. The purge removes that channel
entirely. Measured cost: −0.001 F1 (RF 0.6227→0.6215, XGB 0.6185→0.6179) —
negligible, but the protocol becomes defensible under review.

**Why expanding (all past data), not rolling/recency-weighted?** Tested all
three schemes against the same recent validation fold (2021-04 → 2026-05):

| Scheme                    | RF F1(macro) | XGB F1(macro) |
|---------------------------|-------------:|--------------:|
| A. Expanding (adopted)    |   **0.6227** |   **0.6185**  |
| B. Rolling 10 years       |       0.6219 |       0.6136  |
| C. Expanding + recency w  |       0.6212 |       0.6179  |

Intuition suggested the older, denser-network era (2000–2009 ≈ 43% of
samples) should hurt recent predictions. It does not: the per-cell outage
rate is stable across two decades (~4.0 per cell per 5 years; the visible
−30% total trend is network-footprint shrinkage, not rate change), so old
data still transfers and buys variance reduction. Details:
`docs/scheme_comparison_2026-08.md`.

### Concrete split on the current dataset (2026-08)

From 311,104 outage records: 0.02° grid → 3,355 ever-active cells;
monthly cutoffs 2001-01 → 2026-05 (**305 cutoffs**, step 1 month);
each cutoff yields one row per currently-active cell → **499,859 samples**
(a sample is a *cell×cutoff* pair, not an outage record).

305 cutoffs split into 5 folds of 61 (≈5 years); boundaries at 2006-01,
2011-02, 2016-03, 2021-04. Actual per-fold sizes from the production run:

| Fold | Validation period | Train up to (purge ends) | Train rows | Val rows | Frozen High thr |
|---|---|---|---:|---:|---:|
| 1 | 2006-02 → 2011-02 | 2006-01 (purge → 2004-10) | 84,741 | 104,779 | 4.0 |
| 2 | 2011-03 → 2016-03 | 2011-02 (purge → 2009-11) | 196,297 | 99,053 | 4.0 |
| 3 | 2016-04 → 2021-04 | 2016-03 (purge → 2014-12) | 296,344 | 88,992 | 4.0 |
| 4 | 2021-05 → 2026-05 | 2021-04 (purge → 2020-01) | 387,241 | 91,249 | 4.0 |

Fold 0 (2001-01 → 2006-01) only feeds later folds' training. Each fold
trains a fresh model on data strictly older than its validation period;
a sample that is validation for one fold becomes training data for later
folds, but no model is ever scored on data it saw. The production model is
refit on all 499,859 samples (High threshold 3.0) — its generalisation
claim rests on the four CV models above.

## 4. Training method

| | Random Forest | XGBoost |
|---|---|---|
| Role | Explainability (feature importance) | Accuracy |
| Key params | 200 trees, depth 12, min_leaf 2 | 500 rounds, depth 10, lr 0.03, subsample 0.7 |
| Imbalance | `class_weight="balanced"` | balanced sample weights |

**Why these settings?** Fixed hyperparameters chosen through earlier config
sweeps (`evaluate_models.py` compares 10 configurations). The measured
memorisation gap is small (train-subsample F1 0.67 RF / 0.71 XGB vs 0.62
validation), i.e. neither model materially overfits, so extra regularisation
or early stopping would add complexity without headroom. Both models are
trained identically per fold; the production pair is refit on **all**
samples after validation (standard practice — CV metrics remain the honest
generalisation estimate).

**Class imbalance** (~50/33/17%) is handled inside the loss via class
weights rather than resampling; SMOTE variants were tested in
`evaluate_models.py` and did not beat weighting.

## 5. Evaluation & baselines

Primary metric: **macro F1** (equal weight per class under imbalance),
plus per-class precision/recall, confusion matrices, and mean ± std across folds.

Two naive baselines are evaluated on the identical folds so "skill" has a
reference point:

1. **Majority class** — always predict the most frequent training class.
2. **Persistence** — tier the cell's *current* outage count with the same
   frozen threshold ("recent activity persists"). Note this baseline can
   never predict Low (zero-history cells are filtered from the dataset),
   which itself highlights what the model adds: anticipating quiet periods.

If a model does not clearly beat persistence, its apparent skill is just
autocorrelation — check `persistence_mean_f1` next to `rf_mean_f1` /
`xgb_mean_f1` in `accuracy_metrics.json`.

## 6. Known limitations (documented deliberately)

- **Repeated measures**: each cell appears once per monthly cutoff, so rows
  are correlated; fold-level std understates uncertainty. Block bootstrap
  by cell would tighten confidence intervals.
- **Zero-history cells excluded**: cells with no outages in a feature
  window are dropped from both training and deployment predictions, so
  metrics do not cover never-active cells (consistent by design, but state
  it when reporting).
- **Grid membership uses full history**: the fixed grid derives from all
  years, mildly leaking which cells ever had outages; impact is minimal
  because zero-feature rows are filtered anyway.
- **Single-fold deep dives**: scheme/purge experiments above used the last
  fold; margins <±0.005 F1 should be read as indicative, not significant.
- Pre-2000 records are junk (3 rows) and never enter feature windows
  (cutoffs start 2001).

## 7. Reproduction

```bash
python -m advanced_charts.risk_model      # train + walk-forward + save models/predictions
python -m advanced_charts.risk_model --predict   # regenerate prediction CSVs
python -m advanced_charts.risk_model --evaluate  # print saved metrics
python verify_model_results.py            # independent re-run of fold metrics
python evaluate_models.py                 # 10-config hyperparameter comparison
python evaluate_training_schemes.py       # scheme A/B/C comparison (~8 min)
python evaluate_purge_effect.py           # leakage/memorisation diagnostics (~8 min)
```
