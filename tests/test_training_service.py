"""Focused tests for the non-blocking risk-model training boundary."""

import os
import time
import subprocess
import sys

import pytest
import pandas as pd

from advanced_charts import training_service


def test_process_liveness_check_does_not_terminate_worker():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        for _ in range(3):
            assert training_service._pid_is_alive(process.pid)
        assert process.poll() is None
        process.terminate()
        process.wait(timeout=10)
        assert not training_service._pid_is_alive(process.pid)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_training_lock_recovers_dead_owner_but_preserves_live_owner(tmp_path, monkeypatch):
    import risk_training_worker as worker
    lock = tmp_path / "training.lock"
    monkeypatch.setattr(worker, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(worker, "LOCK_PATH", lock)
    lock.write_text("12345")
    os.utime(lock, (time.time() - 30, time.time() - 30))
    monkeypatch.setattr(worker, "_pid_is_alive", lambda pid: True)
    assert not worker._acquire_lock()
    monkeypatch.setattr(worker, "_pid_is_alive", lambda pid: False)
    assert worker._acquire_lock()
    assert lock.read_text() == str(os.getpid())


def test_training_progress_does_not_schedule_full_page_timer(monkeypatch):
    from dashboard import sidebar
    timers = []
    monkeypatch.setattr(sidebar, "st_autorefresh", lambda **kw: timers.append(kw))
    sidebar.setup_autorefresh(1440, True, 15, model_training_running=True)
    assert [timer["interval"] for timer in timers] == [86400000, 900000]


def test_training_fragment_reruns_app_only_once_on_completion(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from dashboard import sidebar
    ui = SimpleNamespace(session_state={}, rerun=Mock(), progress=Mock(), caption=Mock(), error=Mock())
    monkeypatch.setattr(sidebar, "st", ui)
    status = {"state": "running", "progress": 10}
    monkeypatch.setattr(training_service, "normalise_training_status", lambda: status)
    render = sidebar.render_training_progress.__wrapped__
    render()
    render()
    ui.rerun.assert_not_called()
    status["state"] = "completed"
    render()
    render()
    ui.rerun.assert_called_once()


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
