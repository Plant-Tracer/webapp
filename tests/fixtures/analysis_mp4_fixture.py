"""Reusable source video fixture for analysis-MP4 tests."""

from pathlib import Path

import numpy as np

from resize_app.video_writer import H264Writer


FRAME_COLORS = (
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
)


def write_four_color_movie(path: Path, *, fps: int = 4) -> None:
    """Write a deterministic 96x48, four-frame MP4."""
    writer = H264Writer(path, fps=fps)
    try:
        for color in FRAME_COLORS:
            writer.append_data(np.full((48, 96, 3), color, dtype=np.uint8))
    finally:
        writer.close()
