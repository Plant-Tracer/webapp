"""
Rotate video and build frame zip using PyAV + Pillow only (no ffmpeg binary).
Used by the Lambda rotate-and-zip API so we stay within deployment size limits.
"""

import io
import zipfile
from fractions import Fraction

import av
from PIL import Image

# One 90° CW rotation in PIL terms (PIL rotates CCW, so 90 CW = 270 CCW)
PIL_ROTATE_90_CW = Image.Transpose.ROTATE_270


def _rotate_pil_90_cw(img: Image.Image, steps: int) -> Image.Image:
    """Apply steps × 90° clockwise. steps in 1..3."""
    for _ in range(steps % 4):
        img = img.transpose(PIL_ROTATE_90_CW)
    return img


def rotate_video_av(data: bytes, steps: int) -> bytes:
    """Rotate video by steps × 90° clockwise. steps in 1..3. Returns new MP4 bytes."""
    if steps < 1 or steps > 3:
        raise ValueError("steps must be 1, 2, or 3")
    inp = av.open(io.BytesIO(data))
    vstreams = [s for s in inp.streams if s.type == "video"]
    if not vstreams:
        inp.close()
        raise ValueError("No video stream")
    in_stream = vstreams[0]
    in_codec = in_stream.codec_context
    fps = in_codec.rate
    if fps is None or fps == 0:
        fps = 24
    width, height = in_codec.width, in_codec.height
    # After 90/270 rotation, width and height swap
    if steps % 2 == 1:
        width, height = height, width

    out_buf = io.BytesIO()
    out = av.open(out_buf, "w", format="mp4")
    # mpeg4 is widely available in PyAV builds (no libx264 required)
    out_stream = out.add_stream("mpeg4", rate=fps)
    out_stream.width = width
    out_stream.height = height
    out_stream.pix_fmt = "yuv420p"
    out_stream.time_base = Fraction(1, fps)

    frame_index = 0
    for frame in inp.decode(video=0):
        img = frame.to_image()
        img = _rotate_pil_90_cw(img, steps)
        out_frame = av.VideoFrame.from_image(img)
        out_frame.pts = frame_index
        out_frame.time_base = out_stream.time_base
        for packet in out_stream.encode(out_frame):
            out.mux(packet)
        frame_index += 1

    for packet in out_stream.encode():
        out.mux(packet)

    inp.close()
    out.close()
    return out_buf.getvalue()


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
    inp = av.open(io.BytesIO(data))
    vstreams = [s for s in inp.streams if s.type == "video"]
    if not vstreams:
        inp.close()
        raise ValueError("No video stream")

    # Decode once so we know the total frame count for progress reporting.
    frames = list(inp.decode(video=0))
    total = len(frames)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for idx, frame in enumerate(frames, start=1):
            img = frame.to_image()
            # Downscale to target_wh (analysis size) to keep zips small.
            if img.size[0] > target_wh[0] or img.size[1] > target_wh[1]:
                img.thumbnail(target_wh, Image.Resampling.LANCZOS)
            jpeg_io = io.BytesIO()
            img.save(jpeg_io, format="JPEG", quality=jpeg_quality, optimize=True)
            jpeg_io.seek(0)
            zf.writestr(f"frame_{idx-1:04d}.jpg", jpeg_io.read())

            if progress_cb and total > 0:
                if idx % progress_every == 0 or idx == total:
                    progress_cb(idx, total)

    inp.close()
    return buf.getvalue()
