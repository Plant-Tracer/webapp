"""
Rotate video and build frame zip using OpenCV (cv2) + Pillow only (no ffmpeg, no PyAV).
Used by the Lambda rotate-and-zip API so we stay within deployment size limits.
"""

import io
import tempfile
import zipfile

import cv2
import numpy as np
from PIL import Image

# One 90° CW rotation in PIL terms (PIL rotates CCW, so 90 CW = 270 CCW)
PIL_ROTATE_90_CW = Image.Transpose.ROTATE_270


def _rotate_pil_90_cw(img: Image.Image, steps: int) -> Image.Image:
    """Apply steps × 90° clockwise. steps in 1..3."""
    for _ in range(steps % 4):
        img = img.transpose(PIL_ROTATE_90_CW)
    return img


def _frame_bgr_to_pil(bgr: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR frame to PIL Image (RGB)."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _pil_to_frame_bgr(img: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV BGR frame."""
    rgb = np.array(img)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def rotate_video_av(data: bytes, steps: int) -> bytes:
    """Rotate video by steps × 90° clockwise. steps in 1..3. Returns new MP4 bytes."""
    if steps < 1 or steps > 3:
        raise ValueError("steps must be 1, 2, or 3")
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=True) as inf:
        inf.write(data)
        inf.flush()
        cap = cv2.VideoCapture(inf.name)
        if not cap.isOpened():
            raise ValueError("No video stream")
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        fps = max(1.0, float(fps))
        out_w, out_h = None, None
        writer = None
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=True) as outf:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None or frame.size == 0:
                    break
                img = _frame_bgr_to_pil(frame)
                img = _rotate_pil_90_cw(img, steps)
                w, h = img.size
                if w % 2 != 0:
                    w -= 1
                if h % 2 != 0:
                    h -= 1
                if w <= 0 or h <= 0:
                    continue
                if (w, h) != img.size:
                    img = img.crop((0, 0, w, h))
                if out_w is None:
                    out_w, out_h = w, h
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(outf.name, fourcc, fps, (out_w, out_h))
                writer.write(_pil_to_frame_bgr(img))
            cap.release()
            if writer is None:
                raise ValueError("No video stream or no frames")
            writer.release()
            with open(outf.name, "rb") as f:
                return f.read()


def video_frames_to_zip_av(
    data: bytes,
    jpeg_quality: int = 60,
    progress_cb=None,
    progress_every: int = 5,
    target_wh=(640, 480),
) -> bytes:
    """
    Extract every video frame as (downscaled) JPEG into a zip. Returns zip file bytes.

    If progress_cb is provided, it will be called as progress_cb(current, total)
    approximately every `progress_every` frames (and always on the final frame).
    target_wh: (width, height) to fit frames into (single place for analysis size when called from resize.py with C.ANALYSIS_FRAME_MAX_*).
    """
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=True) as tf:
        tf.write(data)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)
        if not cap.isOpened():
            raise ValueError("No video stream")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                img = _frame_bgr_to_pil(frame)
                if img.size[0] > target_wh[0] or img.size[1] > target_wh[1]:
                    img.thumbnail(target_wh, Image.Resampling.LANCZOS)
                jpeg_io = io.BytesIO()
                img.save(jpeg_io, format="JPEG", quality=jpeg_quality, optimize=True)
                jpeg_io.seek(0)
                zf.writestr(f"frame_{idx:04d}.jpg", jpeg_io.read())
                idx += 1
                if progress_cb and total > 0:
                    if idx % progress_every == 0 or idx == total:
                        progress_cb(idx, total)
            if total <= 0 and progress_cb and idx > 0:
                progress_cb(idx, idx)
        cap.release()
        return buf.getvalue()


def extract_single_frame(movie_bytes: bytes, frame_number: int, jpeg_quality: int = 90) -> bytes:
    """Extract one frame from video bytes as JPEG. frame_number is 0-based."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=True) as tf:
        tf.write(movie_bytes)
        tf.flush()
        cap = cv2.VideoCapture(tf.name)
        if not cap.isOpened():
            raise ValueError("No video stream")
        for _ in range(frame_number + 1):
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                raise ValueError(f"Frame {frame_number} not found")
        # frame is the requested frame (we read frame_number+1 times, last read is frame_number)
        _, jpeg_bytes = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        cap.release()
        return jpeg_bytes.tobytes()


def resize_jpeg_to_fit(jpeg_bytes: bytes, max_width: int, max_height: int, quality: int = 90) -> bytes:
    """Resize JPEG bytes to fit inside (max_width, max_height), preserving aspect. Returns JPEG bytes."""
    img = Image.open(io.BytesIO(jpeg_bytes))
    img.load()
    w, h = img.size
    if w <= max_width and h <= max_height:
        return jpeg_bytes
    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()
