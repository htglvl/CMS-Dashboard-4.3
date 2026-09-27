"""Map labels must be safe to log even with a Windows CP1252 console."""

import os
from pathlib import Path
import subprocess
import sys


def test_app_can_log_unicode_site_labels_on_cp1252():
    environment = dict(os.environ, PYTHONIOENCODING="cp1252")
    result = subprocess.run(
        [sys.executable, "-c", (
            "import enhanced_app; "
            "print('[INFO-SECTION] session selected_site: \\U0001f4cd Location (54.0,-2.0)'); "
            "print('Tiếng Việt — café')"
        )],
        cwd=Path(__file__).resolve().parent.parent,
        env=environment,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    text = result.stdout.decode("utf-8")
    assert "📍 Location" in text
    assert "Tiếng Việt — café" in text
