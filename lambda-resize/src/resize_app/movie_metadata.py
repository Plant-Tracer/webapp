"""
Extract movie metadata (width, height, fps, total_frames, total_bytes) from MP4 bytes.
Used by Lambda rotate-and-zip so DB has full metadata after processing.
"""

import io
from typing import Any, Dict

import av


def extract_movie_metadata(movie_bytes: bytes) -> Dict[str, Any]:
    """
    Read stream metadata and frame count from video bytes.
    :param movie_bytes: full MP4 (or compatible) file bytes
    :return: dict with width, height, fps (str), total_frames (int), total_bytes (int).
             Missing values are omitted; caller can merge with existing DB state.
    """
    result = {"total_bytes": len(movie_bytes)}
    inp = av.open(io.BytesIO(movie_bytes))
    try:
        vstreams = [s for s in inp.streams if s.type == "video"]
        if not vstreams:
            return result
        stream = vstreams[0]
        codec = stream.codec_context
        w = getattr(stream, "width", None) or (codec and codec.width)
        h = getattr(stream, "height", None) or (codec and codec.height)
        if w is not None and w > 0:
            result["width"] = int(w)
        if h is not None and h > 0:
            result["height"] = int(h)
        fps = codec.rate if codec else getattr(stream, "average_rate", None)
        if fps is not None:
            try:
                result["fps"] = str(float(fps))
            except (TypeError, ValueError):
                pass
        total_frames = 0
        for _ in inp.decode(video=0):
            total_frames += 1
        if total_frames > 0:
            result["total_frames"] = total_frames
    finally:
        inp.close()
    return result
