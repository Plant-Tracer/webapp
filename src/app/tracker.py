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

# Explicit re-exports for pylint/static analysis (members used by app and tests)
run_tracking = _tracker.run_tracking
TrackingEnv = _tracker.TrackingEnv
get_movie_data = _tracker.get_movie_data
extract_frame = _tracker.extract_frame
cleanup_mp4 = _tracker.cleanup_mp4
track_movie = _tracker.track_movie
render_tracked_movie = _tracker.render_tracked_movie
rotate_movie = _tracker.rotate_movie
prepare_movie_for_tracking = _tracker.prepare_movie_for_tracking
