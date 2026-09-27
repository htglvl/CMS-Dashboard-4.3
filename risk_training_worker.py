"""Standalone risk-model trainer used by the dashboard background service."""

from __future__ import annotations

import argparse
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from advanced_charts.training_service import MODELS_DIR, STATUS_PATH, _write_status, _pid_is_alive


LOCK_PATH = MODELS_DIR / "training.lock"


def _prepare_predictions(force: bool, publish) -> None:
    from advanced_charts import risk_model
    from advanced_charts.training_service import PREDICTION_PATHS

    risk_model.invalidate_features_cache()
    missing_predictions = any(not path.exists() for path in PREDICTION_PATHS.values())
    saved_models_exist = risk_model.RF_MODEL_PATH.exists() and risk_model.XGB_MODEL_PATH.exists()
    if not force and missing_predictions and saved_models_exist:
        risk_model.publish_saved_model_predictions(progress_callback=publish)
    else:
        risk_model._train_and_save(progress_callback=publish)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _acquire_lock() -> bool:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - LOCK_PATH.stat().st_mtime
            owner = LOCK_PATH.read_text(encoding="utf-8").strip()
            # Allow time for a new owner to write its PID. Recover locks left
            # behind by a terminated worker, but never evict a live trainer.
            stale = age > 10 and owner.isdigit() and not _pid_is_alive(owner)
            if stale or (age > 24 * 3600 and not owner.isdigit()):
                LOCK_PATH.unlink()
                return _acquire_lock()
        except OSError:
            pass
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
        lock_file.write(str(os.getpid()))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and publish risk models in the background")
    parser.add_argument("--force", action="store_true", help="Record this as a manual run")
    args = parser.parse_args()

    if not _acquire_lock():
        return 0

    started_at = _utc_now()

    def publish(progress: int, message: str) -> None:
        _write_status({
            "state": "running",
            "progress": max(0, min(100, int(progress))),
            "message": message,
            "pid": os.getpid(),
            "started_at": started_at,
            "updated_at": _utc_now(),
            "trigger": "manual" if args.force else "scheduled",
        })

    try:
        publish(1, "Starting isolated risk prediction worker")
        _prepare_predictions(args.force, publish)
        # Recommendations are derived from risk predictions, so make the web
        # process rebuild them on its next lightweight refresh.
        from advanced_charts.recommendation_engine import invalidate_report_cache
        invalidate_report_cache()
        _write_status({
            "state": "completed",
            "progress": 100,
            "message": "New risk predictions are ready",
            "pid": os.getpid(),
            "started_at": started_at,
            "finished_at": _utc_now(),
            "trigger": "manual" if args.force else "scheduled",
        })
        return 0
    except Exception as exc:
        traceback.print_exc()
        _write_status({
            "state": "failed",
            "progress": 0,
            "message": str(exc),
            "pid": os.getpid(),
            "started_at": started_at,
            "finished_at": _utc_now(),
            "trigger": "manual" if args.force else "scheduled",
        })
        return 1
    finally:
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
