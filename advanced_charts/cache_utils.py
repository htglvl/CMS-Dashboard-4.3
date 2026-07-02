"""Cache staleness utilities for pickle and data files.

Provides helpers to check whether cached artifacts (models, feature
DataFrames, chart aggregations) are outdated and need rebuilding.
"""

import os
import time
from pathlib import Path

# Default maximum cache age before a rebuild is triggered (3 months).
CACHE_MAX_AGE_DAYS = 90


def is_cache_stale(cache_path: Path, max_age_days: int = CACHE_MAX_AGE_DAYS) -> bool:
    """Return True if *cache_path* is missing or older than *max_age_days*."""
    if not cache_path.exists():
        return True
    age_seconds = time.time() - os.path.getmtime(cache_path)
    return age_seconds > max_age_days * 86400


def is_cache_stale_vs_source(cache_path: Path, source_path: Path) -> bool:
    """Return True if *cache_path* is older than *source_path* (or missing)."""
    if not cache_path.exists():
        return True
    if not source_path.exists():
        return False
    return os.path.getmtime(cache_path) < os.path.getmtime(source_path)
