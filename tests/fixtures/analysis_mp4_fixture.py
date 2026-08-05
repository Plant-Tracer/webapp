"""Reusable source video fixture for analysis-MP4 tests."""

from pathlib import Path

import imageio
import numpy as np


FRAME_COLORS = (
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
)


def write_four_color_movie(path: Path) -> None:
    """Write a deterministic 96x48, four-frame MP4."""
    writer = imageio.get_writer(path, format="FFMPEG", mode="I", fps=4, codec="libx264")
    try:
        for color in FRAME_COLORS:
            writer.append_data(np.full((48, 96, 3), color, dtype=np.uint8))
    finally:
        writer.close()
