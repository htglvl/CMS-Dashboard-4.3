# Training-Scheme & Leakage Experiments — August 2026

Empirical record of two experiments run on 2026-08-23 to settle design
questions about the risk model's train/validation protocol. Raw outputs:
`models/scheme_comparison.json`, `models/purge_experiment.json`.

Common setup: 499,859 sliding-window samples (305 monthly cutoffs × ~3,355
active cells/window), production hyperparameters, validation fixed to the
last walk-forward fold (2021-04 → 2026-05, n = 91,249; classes 49.8/33.0/17.2%).

## Experiment 1 — does the old data era hurt recent predictions?

Motivation: expanding-window training draws ~43% of samples from the
2000–2009 era, when the network footprint was ~28% larger. Hypothesis:
stale-era dominance degrades recent performance; a rolling window or
recency weighting should help.

| Arm | RF F1(macro) | XGB F1(macro) | n_train |
|---|---:|---:|---:|
| A. Expanding (all history) — **adopted** | **0.6227** | **0.6185** | 408,610 |
| B. Rolling 10 years | 0.6219 | 0.6136 | 186,387 |
| C. Expanding + recency weights (half-life 5y) | 0.6212 | 0.6179 | 408,610 |

**Verdict: hypothesis rejected.** Expanding wins with both models. The
per-cell outage rate is stable across two decades (4.1 → 3.9 per cell per
5 years for 2000s → 2020s), so old samples still transfer; dropping them
only removes variance reduction.

## Experiment 2 — how much do window-overlap leakage and memorisation inflate metrics?

Motivation: adjacent sliding windows share outages, so late-training label
windows can overlap early-validation feature windows ("did the model just
memorise leaked answers?").

Diagnostics per arm: `purge15` removes every training sample whose cutoff
is within 15 months of the validation boundary; NEAR = val rows where that
overlap channel existed, FAR = provably clean val rows; train-sub = F1 on
200k of the arm's own training rows (memorisation gauge).

| Arm | F1 val | F1 NEAR | F1 FAR | F1 train-sub |
|---|---:|---:|---:|---:|
| RF no-purge | 0.6227 | 0.6362 | 0.6187 | 0.6666 |
| XGB no-purge | 0.6185 | 0.6298 | 0.6151 | 0.7148 |
| RF purge15 | 0.6215 | 0.6339 | 0.6179 | 0.6695 |
| XGB purge15 | 0.6179 | 0.6294 | 0.6145 | 0.7194 |

Findings:

1. **Purge costs almost nothing** (−0.0012 / −0.0006 F1) → reported metrics
   are not carried by leakage. Purge is adopted anyway as protocol hygiene.
2. **Models do not memorise**: train-sub F1 is only +0.04 (RF) / +0.10 (XGB)
   above validation. ~0.62 macro-F1 reflects genuine task noise, not
   overfitting.
3. The small NEAR>FAR gap (+0.017) survives purging → it is temporal
   difficulty drift (2023–25 slightly harder), not leakage.

## Consequences applied to the codebase

- Walk-forward keeps the **expanding window**, now with the **15-month purge**.
- Labels tiered by a **frozen High threshold** per fold (train-only).
- **Majority-class and persistence baselines** logged next to model metrics.
- Full rationale: `docs/model_methodology.md`.
