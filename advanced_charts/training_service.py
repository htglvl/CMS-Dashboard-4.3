"""Launch and monitor risk-model training outside the Streamlit process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
STATUS_PATH = MODELS_DIR / "training_status.json"
WORKER_PATH = PROJECT_ROOT / "risk_training_worker.py"
LOG_PATH = PROJECT_ROOT / "logs" / "risk_training.log"
PREDICTION_PATHS = {
    "Random Forest": MODELS_DIR / "predictions_randomforest.csv",
    "XGBoost": MODELS_DIR / "predictions_xgboost.csv",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(status: dict) -> None:
    """Atomically publish status for readers in other processes."""
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATUS_PATH.with_suffix(f".{os.getpid()}.tmp")
    temp_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    os.replace(temp_path, STATUS_PATH)


def read_training_status() -> dict:
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"state": "idle", "progress": 0, "message": "No training run recorded"}


def _pid_is_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def normalise_training_status(status: dict | None = None) -> dict:
    """Turn an abandoned running state into a visible failure state."""
    status = dict(status or read_training_status())
    if status.get("state") in {"queued", "running"} and not _pid_is_alive(status.get("pid")):
        # Give a just-spawned worker a short window to replace the queued PID.
        queued_at = status.get("started_at")
        try:
            queued_age = time.time() - datetime.fromisoformat(queued_at).timestamp()
        except (TypeError, ValueError):
            queued_age = 60
        if queued_age > 10:
            status.update(
                state="failed",
                message="Training process stopped unexpectedly",
                finished_at=_utc_now(),
            )
            _write_status(status)
    return status


def prediction_path(model_choice: str) -> Path:
    return PREDICTION_PATHS.get(model_choice, PREDICTION_PATHS["Random Forest"])


def prediction_mtime(model_choice: str) -> float:
    path = prediction_path(model_choice)
    return path.stat().st_mtime if path.exists() else 0.0


def training_is_due(refresh_days: int) -> bool:
    """Return whether either published prediction set has exceeded its TTL."""
    paths = list(PREDICTION_PATHS.values())
    if any(not path.exists() for path in paths):
        return True
    oldest_publication = min(path.stat().st_mtime for path in paths)
    return time.time() - oldest_publication >= max(1, int(refresh_days)) * 86400


def request_model_training(refresh_days: int = 30, force: bool = False) -> tuple[bool, dict]:
    """Start the detached worker when due, returning immediately."""
    current = normalise_training_status()
    if current.get("state") in {"queued", "running"}:
        return False, current
    if not force and not training_is_due(refresh_days):
        return False, current

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    command = [sys.executable, str(WORKER_PATH)]
    if force:
        command.append("--force")

    popen_kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **popen_kwargs)
    finally:
        log_handle.close()

    queued = {
        "state": "queued",
        "progress": 0,
        "message": "Risk-model worker is starting",
        "pid": process.pid,
        "started_at": _utc_now(),
        "refresh_days": int(refresh_days),
        "trigger": "manual" if force else "scheduled",
    }
    # The worker can reach "running" before Popen returns on a fast machine;
    # never overwrite that newer progress with the queued snapshot.
    latest = read_training_status()
    another_live_worker = (
        latest.get("state") in {"queued", "running"}
        and _pid_is_alive(latest.get("pid"))
    )
    if not another_live_worker:
        _write_status(queued)
        latest = queued
    return True, latest
