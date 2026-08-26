"""Small H.264 writer backed directly by the imageio-ffmpeg executable."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import numpy as np


class H264Writer:
    """Stream RGB uint8 frames to a libx264 MP4 without importing ImageIO."""

    def __init__(self, path: Path, *, fps: float, output_params: Sequence[str] = (),
                 quality: float | None = 5):
        self.path = path
        self.fps = fps
        self.output_params = list(output_params)
        self.quality = quality
        self._writer: Any = None
        self._size: tuple[int, int] | None = None

    def append_data(self, frame: np.ndarray) -> None:
        """Append one RGB frame, starting FFmpeg when its dimensions are known."""
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("H.264 frames must be HxWx3 uint8 RGB arrays")
        height, width = frame.shape[:2]
        size = (width, height)
        if self._writer is None:
            self._writer = imageio_ffmpeg.write_frames(
                self.path,
                size,
                pix_fmt_in="rgb24",
                pix_fmt_out="yuv420p",
                fps=self.fps,
                quality=self.quality,
                codec="libx264",
                macro_block_size=1,
                output_params=self.output_params,
            )
            self._writer.send(None)
            self._size = size
        elif size != self._size:
            raise ValueError(f"H.264 frame size changed from {self._size} to {size}")
        self._writer.send(np.ascontiguousarray(frame))

    def close(self) -> None:
        """Finish the MP4 when frames were written."""
        if self._writer is not None:
            self._writer.close()
            self._writer = None
