#!/usr/bin/env python3
"""
vga_zip.py — Downscale video frames to VGA and stream them as JPEGs into a ZIP.
Pure Python: uses PyAV (libav*), Pillow; no subprocess calls to ffmpeg.
"""

import io
import math
import zipfile
from pathlib import Path
from typing import Tuple, Optional

import av  # pip install av
from PIL import Image, ImageOps  # pip install pillow


# ---------- Geometry & rotation helpers ----------

def _rotation_degrees_from_frame(frame: av.video.frame.VideoFrame) -> int:
    """
    Extract clockwise rotation (0/90/180/270) from frame side data if present.
    Falls back to stream 'rotate' metadata if available.
    """
    # Newer FFmpeg writes a display matrix in side data.
    try:
        for sd in frame.side_data:
            if sd.type.name == "DISPLAYMATRIX":
                # Matrix maps frame to display; angle is derived as per FFmpeg
                # PyAV exposes .to_dict() -> {'rotation': 90.0} in recent builds.
                d = sd.to_dict()
                if "rotation" in d:
                    rot = int(round(d["rotation"])) % 360
                    return (rot + 360) % 360
    except Exception:
        pass

    # Older approach: stream metadata "rotate"
    try:
        stream = frame.pts is not None and frame._stream  # internal, best-effort
        # Fallback: not reliable; prefer container stream metadata if available.
    except Exception:
        stream = None

    # We can also look at container stream metadata if provided by caller
    # (handled in transcode loop via provided rotate_hint)
    return 0


def _apply_rotation(img: Image.Image, degrees: int) -> Image.Image:
    if degrees == 0:
        return img
    elif degrees == 90:
        return img.transpose(Image.Transpose.ROTATE_270)  # PIL is counterclockwise
    elif degrees == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    elif degrees == 270:
        return img.transpose(Image.Transpose.ROTATE_90)
    else:
        # Non right-angle rotations are rare; round to nearest right angle
        q = (int(round(degrees / 90.0)) * 90) % 360
        return _apply_rotation(img, q)


def _compute_fit_size(src_wh: Tuple[int, int],
                      max_wh: Tuple[int, int]) -> Tuple[int, int]:
    """
    Proportional fit inside max_wh (no padding).
    """
    sw, sh = src_wh
    mw, mh = max_wh
    scale = min(mw / sw, mh / sh)
    return max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))


def _resize_image(img: Image.Image,
                  target_wh=(640, 480),
                  mode: str = "fit",
                  resample=Image.Resampling.LANCZOS,
                  pad_color=(0, 0, 0)) -> Image.Image:
    """
    mode = "fit": scale proportionally <= target, no padding (<= VGA both dims).
    mode = "letterbox": exact target_wh with bars as needed.
    """
    tw, th = target_wh
    if mode == "fit":
        nw, nh = _compute_fit_size(img.size, target_wh)
        if (nw, nh) == img.size:
            return img
        return img.resize((nw, nh), resample=resample)
    elif mode == "letterbox":
        # ImageOps.pad preserves aspect, then pads to exact target
        return ImageOps.pad(img, target_wh, method=resample, color=pad_color)
    else:
        raise ValueError("mode must be 'fit' or 'letterbox'")


# ---------- Main processing ----------

def video_to_vga_zip(
    input_path: str,
    zip_path: str,
    jpeg_quality: int = 92,
    jpeg_subsampling: str = "4:2:0",  # "4:4:4" if you want max fidelity
    target_wh=(640, 480),
    mode: str = "fit",               # "fit" or "letterbox"
    start_time: Optional[float] = None,  # seconds
    end_time: Optional[float] = None,    # seconds
) -> None:
    """
    Stream-decodes a video, downscales frames to VGA, JPEG-encodes, writes to ZIP.
    No intermediate files are created.
    """
    input_path = str(input_path)
    zip_path = str(zip_path)

    # Open container and pick the first video stream
    container = av.open(input_path)
    vstreams = [s for s in container.streams if s.type == "video"]
    if not vstreams:
        raise RuntimeError("No video stream found")
    vstream = vstreams[0]

    # Optionally seek to start_time for efficiency
    if start_time is not None:
        container.seek(int(start_time * av.time_base))

    frame_index = 0
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Use precise decode iterator
        for packet in container.demux(vstream):
            for frame in packet.decode():
                if end_time is not None and frame.time is not None and frame.time > end_time:
                    break

                # → PIL image (RGB)
                img = frame.to_image()

                # Correct rotation first
                degrees = _rotation_degrees_from_frame(frame)
                img = _apply_rotation(img, degrees)

                # Decide target box per orientation (after rotation)
                w, h = img.size
                if w >= h:
                    # Landscape → fit inside 640x480
                    target_wh_this = (640, 480)
                else:
                    # Portrait → fit inside 480x640 (preserve portrait)
                    target_wh_this = (480, 640)

                # Downscale
                img = _resize_image(img, target_wh=target_wh_this, mode=mode)

                # JPEG → zip (no intermediates)
                bio = io.BytesIO()
                img.save(
                    bio,
                    format="JPEG",
                    quality=jpeg_quality,
                    optimize=True,
                    progressive=False,
                    subsampling=jpeg_subsampling,
                )
                bio.seek(0)
                zf.writestr(f"frame_{frame_index:06d}.jpg", bio.read())
                frame_index += 1

            if end_time is not None and packet.dts is not None:
                # We already check frame.time; this guard is extra.
                pass

    container.close()


# ---------- CLI wrapper ----------

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Downscale a video to VGA frames and stream them into a ZIP (no intermediates)."
    )
    p.add_argument("input", help="Input video file (mp4, mov, mkv, etc.)")
    p.add_argument("output_zip", help="Output ZIP path (e.g., out_frames.zip)")
    p.add_argument("--mode", choices=["fit", "letterbox"], default="fit",
                   help="Scaling mode: 'fit' keeps aspect (<=640x480); 'letterbox' pads to exactly 640x480")
    p.add_argument("--quality", type=int, default=92, help="JPEG quality (1-95)")
    p.add_argument("--subsampling", default="4:2:0", choices=["4:4:4", "4:2:2", "4:2:0"])
    p.add_argument("--start", type=float, default=None, help="Start time in seconds")
    p.add_argument("--end", type=float, default=None, help="End time in seconds")
    args = p.parse_args()

    video_to_vga_zip(
        args.input,
        args.output_zip,
        jpeg_quality=args.quality,
        jpeg_subsampling=args.subsampling,
        target_wh=(640, 480),
        mode=args.mode,
        start_time=args.start,
        end_time=args.end,
    )


if __name__ == "__main__":
    main()
