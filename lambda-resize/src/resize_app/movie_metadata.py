"""
Extract movie metadata (width, height, fps, total_frames, total_bytes) from MP4 bytes.
Used by Lambda rotate-and-zip so DB has full metadata after processing.
Uses OpenCV (cv2) only; no PyAV dependency.
"""

import tempfile
from typing import Any, Dict

import cv2


def extract_movie_metadata(movie_bytes: bytes) -> Dict[str, Any]:
    """
    Read stream metadata and frame count from video bytes.
    :param movie_bytes: full MP4 (or compatible) file bytes
    :return: dict with width, height, fps (str), total_frames (int), total_bytes (int).
             Missing values are omitted; caller can merge with existing DB state.
    """
    result = {"total_bytes": len(movie_bytes)}
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=True) as tf:
        tf.write(movie_bytes)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)
        try:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if w > 0:
                result["width"] = w
            if h > 0:
                result["height"] = h
            fps_val = cap.get(cv2.CAP_PROP_FPS)
            if fps_val is not None and fps_val > 0:
                result["fps"] = str(float(fps_val))
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count is not None and frame_count > 0:
                result["total_frames"] = int(frame_count)
            else:
                total = 0
                while True:
                    ret, _ = cap.read()
                    if not ret:
                        break
                    total += 1
                if total > 0:
                    result["total_frames"] = total
        finally:
            cap.release()
    return result
