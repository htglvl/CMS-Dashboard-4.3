"""Small persistent profiler for dashboard server-side load phases."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = PROJECT_ROOT / "logs" / "dashboard_profile.json"


class DashboardProfiler:
    """Collect named wall-clock phases and publish the latest completed run."""

    def __init__(self):
        self.started = time.perf_counter()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.phases: list[dict] = []

    @staticmethod
    def start_phase() -> float:
        return time.perf_counter()

    def record(self, name: str, phase_started: float) -> float:
        seconds = time.perf_counter() - phase_started
        self.phases.append({"name": name, "seconds": round(seconds, 4)})
        return seconds

    def finish(self) -> dict:
        total = time.perf_counter() - self.started
        measured = sum(phase["seconds"] for phase in self.phases)
        phases = list(self.phases)
        unmeasured = max(0.0, total - measured)
        if unmeasured >= 0.0001:
            phases.append({"name": "Other orchestration/UI", "seconds": round(unmeasured, 4)})
        for phase in phases:
            phase["percentage"] = round(phase["seconds"] / total * 100, 1) if total else 0.0
        result = {
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total_seconds": round(total, 4),
            "scope": "Streamlit server execution; excludes browser tile download and paint",
            "phases": sorted(phases, key=lambda item: item["seconds"], reverse=True),
        }
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = PROFILE_PATH.with_suffix(f".{os.getpid()}.tmp")
        temp_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        os.replace(temp_path, PROFILE_PATH)
        return result


def read_last_profile() -> dict | None:
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render_last_profile(st) -> None:
    """Show the latest completed run in a collapsed sidebar panel."""
    profile = read_last_profile()
    if not profile:
        return
    with st.sidebar.expander("⏱ Load profiler (last run)", expanded=False):
        st.metric("Server load", f"{profile.get('total_seconds', 0):.2f}s")
        for phase in profile.get("phases", [])[:6]:
            st.caption(
                f"{phase['name']}: {phase['seconds']:.2f}s ({phase['percentage']:.1f}%)"
            )
        st.caption("Browser map tiles and paint are not included.")

