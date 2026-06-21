# Risk Assessment

This page explains how the dashboard calculates vulnerability scores and risk profiles for each charging site.

---

## Overview

Each charging site is evaluated across four dimensions, normalised to a 0-100 scale relative to all other sites under the current filters. The scores are visualised on a radar (spider) chart and combined into an overall vulnerability score.

---

## The Four Risk Dimensions

### 1. Frequency Score
- **What it measures:** Number of outages affecting the site (within 2-mile buffer)
- **Higher = worse:** More frequent outages indicate an unreliable grid area
- **Normalisation:** `(site_count - min_count) / (max_count - min_count) × 100`

### 2. Duration Score
- **What it measures:** Average outage duration in hours
- **Higher = worse:** Longer outages mean extended power loss for customers
- **Normalisation:** `(site_avg - min_avg) / (max_avg - min_avg) × 100`

### 3. Impact Score
- **What it measures:** Total customer-hours lost across all outages
- **Higher = worse:** Greater cumulative impact on customers
- **Normalisation:** `(site_impact - min_impact) / (max_impact - min_impact) × 100`

### 4. Consistency Score
- **What it measures:** Predictability of outage durations (inverse of coefficient of variation)
- **Higher = more consistent:** Outages tend to be similar in length (more predictable)
- **Formula:** CV = standard_deviation / mean; score = `(max_cv - site_cv) / (max_cv - min_cv) × 100`
- **Interpretation:** A low CV means outages are predictable; a high CV means they vary wildly

---

## Overall Vulnerability Score

```
Overall = (Frequency + Duration + Impact + Consistency) / 4
```

- Range: **0** (least vulnerable) to **100** (most vulnerable)
- A higher score indicates a site that experiences more frequent, longer, or more impactful outages, or whose outages are less predictable

### Interpretation Guide

| Score Range | Risk Level | Recommendation |
|---|---|---|
| 70-100 | Critical | Priority for immediate V2X deployment |
| 50-69 | High | Recommended for V2X upgrade |
| 30-49 | Medium | Monitor for trend changes |
| 0-29 | Low | Current infrastructure appears adequate |

---

## Why Normalisation Matters

Without normalisation, all sites would appear nearly identical if their absolute values are close. Normalisation scales each metric relative to the actual distribution in the current dataset, making even small differences visible on the radar chart.

**Example:** If all sites have 2-3 outages, the frequency axis would show meaningful differences. Without normalisation (e.g. dividing by a fixed number like 10), all sites would cluster near the same point.

### Edge Case

If all sites have the same value for a metric (denominator = 0), the score defaults to 50 to prevent the axis from collapsing.

---

## IQR Outlier Removal

Before computing risk scores, the dashboard can remove outlier outages using the Interquartile Range (IQR) method:

- **IQR** = Q3 - Q1 (75th percentile minus 25th percentile)
- **Bounds:** `[Q1 - k × IQR, Q3 + k × IQR]`
- **k** is the IQR multiplier (default 1.5, adjustable 0-4)
- Data outside these bounds is excluded

This prevents extremely long outages from skewing the duration and impact scores.

---

## Significance Filter

The significance filter focuses on high-impact outages:

```
significance_ratio = Total Customer Minutes Lost / (duration_hours × 60)
```

Only outages with a significance ratio above the chosen quantile threshold are retained. This removes outages that were long but had minimal customer impact, or short but affected many customers.

---

## ML-Based Risk Prediction

In addition to the per-site risk scores above, the dashboard includes a **machine learning model** that predicts outage risk for every grid cell in the study area.

### How It Works

1. **Grid the area** into ~1 km cells (0.01° × 0.01°)
2. **Compute features** per cell from historic outages:
   - Outage count, average/std duration, total customer hours
   - Winter ratio, night ratio, exceptional event ratio
   - Cause diversity, nearest substation distance
3. **Assign risk labels** using quantile terciles: High (top 33%), Medium, Low
4. **Train two classifiers**:
   - **Random Forest** — 200 trees, max depth 12, balanced classes (explainable)
   - **XGBoost** — 200 rounds, max depth 6, learning rate 0.1 (accurate)
5. **Predict** risk level + confidence score for every grid cell

### Features Used

| Feature | Importance (RF) | Description |
|---------|----------------|-------------|
| `outage_count` | 61% | Total outages in cell |
| `cause_diversity` | 15% | Unique cause categories |
| `total_customer_hours` | 13% | Cumulative customer impact |
| `std_duration` | 5% | Duration variability |
| `night_ratio` | 4% | % of nighttime outages |
| `winter_ratio` | 2% | % of winter outages |
| `exceptional_ratio` | 0.4% | % of exceptional events |
| `avg_duration` | 0.4% | Mean duration |
| `nearest_substation_km` | 0% | Distance to nearest substation |

### Output

Each grid cell gets:
- **risk_level**: High / Medium / Low
- **confidence**: 0-100% (max class probability)
- **prob_low, prob_medium, prob_high**: per-class probabilities

### Map Visualisation

Risk predictions are displayed as a toggleable heatmap layer on the dashboard map:
- Red cells = High risk
- Amber cells = Medium risk
- Green cells = Low risk
- Opacity scales with confidence

### Training the Model

```bash
python advanced_charts/risk_model.py
```

This saves trained models to `models/` and generates prediction CSVs. Re-run after updating the outage dataset.

### Implementation

| File | Purpose |
|---|---|
| `advanced_charts/risk_model.py` | Feature engineering, model training, prediction |
| `advanced_charts/recommendation_engine.py` | Business recommendations using risk predictions |
| `dashboard/charts.py` | Risk Prediction tab in detailed analysis |
| `dashboard/map.py` | Risk heatmap layer |

---

## Implementation

The risk assessment logic lives in these files:

| File | Class/Method | Purpose |
|---|---|---|
| `advanced_charts.py` | `DynamicChartGenerator.get_risk_scores()` | Computes normalised scores |
| `advanced_charts.py` | `DynamicChartGenerator.create_risk_assessment_chart()` | Builds the radar chart |
| `advanced_charts.py` | `AIRecommendationEngine.analyze_site_performance()` | Rule-based risk classification |
| `advanced_charts/risk_model.py` | `build_grid_features()` | Feature engineering for ML model |
| `advanced_charts/risk_model.py` | `train_random_forest()` / `train_xgboost()` | Model training |
| `advanced_charts/risk_model.py` | `predict_cells()` | Grid cell risk prediction |
| `advanced_charts/recommendation_engine.py` | `RecommendationEngine` | Business recommendations & NL interface |
