"""
Shim: tracker implementation lives in lambda-resize (resize_app.tracker).
This module re-exports it so "from app import tracker" and "from . import tracker" keep working.
Ensure PYTHONPATH includes lambda-resize/src when running the app or tests.
"""

import sys
from pathlib import Path

# Prepend lambda-resize/src so resize_app is importable
_resize_src = Path(__file__).resolve().parents[2] / "lambda-resize" / "src"
_resize_src_str = str(_resize_src)
if _resize_src_str not in sys.path:
    sys.path.insert(0, _resize_src_str)

from resize_app import tracker as _tracker  # noqa: E402  # pylint: disable=import-error,wrong-import-position

# Re-export all public names so "from app.tracker import run_tracking" etc. work
for _name in dir(_tracker):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_tracker, _name)
