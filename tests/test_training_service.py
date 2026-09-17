"""Focused tests for the non-blocking risk-model training boundary."""

import os
import time

import pytest
import pandas as pd

from advanced_charts import training_service


def test_training_due_when_prediction_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(training_service, "PREDICTION_PATHS", {
        "Random Forest": tmp_path / "rf.csv",
        "XGBoost": tmp_path / "xgb.csv",
    })
    assert training_service.training_is_due(30)


def test_training_interval_uses_oldest_published_result(tmp_path, monkeypatch):
    paths = {
        "Random Forest": tmp_path / "rf.csv",
        "XGBoost": tmp_path / "xgb.csv",
    }
    for path in paths.values():
        path.write_text("lat,lon\n", encoding="utf-8")
    now = time.time()
    os.utime(paths["Random Forest"], (now - 31 * 86400, now - 31 * 86400))
    os.utime(paths["XGBoost"], (now, now))
    monkeypatch.setattr(training_service, "PREDICTION_PATHS", paths)

    assert training_service.training_is_due(30)
    assert not training_service.training_is_due(90)


def test_model_loader_does_not_train_implicitly(tmp_path, monkeypatch):
    from advanced_charts import risk_model

    monkeypatch.setattr(risk_model, "RF_MODEL_PATH", tmp_path / "missing-rf.pkl")
    monkeypatch.setattr(risk_model, "XGB_MODEL_PATH", tmp_path / "missing-xgb.pkl")

    with pytest.raises(FileNotFoundError, match="risk_training_worker"):
        risk_model.load_models()


def test_heatmap_grid_reduces_payload_and_preserves_weight(monkeypatch):
    from dashboard import map as dashboard_map

    monkeypatch.setattr(dashboard_map, "_heatmap_cache_key", None)
    monkeypatch.setattr(dashboard_map, "_heatmap_cache_data", None)
    outages = pd.DataFrame({
        "latitude": [54.001, 54.002, 54.041],
        "longitude": [-2.001, -2.002, -2.041],
        "duration-hours": [1.0, 2.0, 4.0],
    })

    points = dashboard_map._build_heatmap_data(outages)

    assert len(points) == 2
    assert sum(point[2] for point in points) == pytest.approx(7.0)
