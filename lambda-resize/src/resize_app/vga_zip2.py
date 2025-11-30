#!/usr/bin/env python3
import io, zipfile
from fractions import Fraction
from typing import Optional

import av                       # PyAV (must be built with libx264 available)
import numpy as np
from PIL import Image, ImageOps

# ---------------- helpers from previous version ----------------

def _apply_rotation(img: Image.Image, degrees: int) -> Image.Image:
    if degrees % 360 == 0: return img
    # PIL rotates counter-clockwise for ROTATE_* transposes
    m = {90: Image.Transpose.ROTATE_270,
         180: Image.Transpose.ROTATE_180,
         270: Image.Transpose.ROTATE_90}
    return img.transpose(m.get(degrees % 360, Image.Transpose.ROTATE_270))

def _rotation_degrees_from_frame(frame: av.video.frame.VideoFrame) -> int:
    try:
        for sd in frame.side_data:
            if sd.type.name == "DISPLAYMATRIX":
                d = sd.to_dict()
                if "rotation" in d:
                    return int(round(d["rotation"])) % 360
    except Exception:
        pass
    return 0

def _resize_image(img: Image.Image, target_wh=(640,480), mode="fit",
                  resample=Image.Resampling.LANCZOS, pad_color=(0,0,0)) -> Image.Image:
    tw, th = target_wh
    if mode == "fit":
        sw, sh = img.size
        scale = min(tw / sw, th / sh)
        nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
        return img if (nw, nh) == img.size else img.resize((nw, nh), resample=resample)
    elif mode == "letterbox":
        return ImageOps.pad(img, target_wh, method=resample, color=pad_color)
    else:
        raise ValueError("mode must be 'fit' or 'letterbox'")

# ---------------- main ----------------

def video_to_zip_and_mp4(
    input_path: str,
    zip_path: str,
    mp4_path: str,
    jpeg_quality: int = 92,
    jpeg_subsampling: str = "4:2:0",
    fps: int = 30,
    prefer_portrait_box: bool = False,   # False => 640x480, True => 480x640
    mode: str = "letterbox",             # encoder needs constant WxH; use letterbox
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    pad_color=(0,0,0),
    crf: int = 20,
    preset: str = "veryfast",
):
    """
    One pass: decode -> rotate -> downscale -> write JPEGs to ZIP + frames to MP4 (H.264).
    Requires PyAV linked with libx264. No shelling to ffmpeg.
    """
    container = av.open(input_path)
    vstreams = [s for s in container.streams if s.type == "video"]
    if not vstreams:
        raise RuntimeError("No video stream found")
    vstream = vstreams[0]

    # Decide constant encoder frame size (MP4 requires fixed WxH)
    # We use the *first decoded frame* orientation to pick target box.
    # If clip flips mid-stream (rare on phones), letterboxing keeps WxH stable.
    first_img: Optional[Image.Image] = None
    first_rot: Optional[int] = None

    # Optional seek
    if start_time is not None:
        container.seek(int(start_time * av.time_base))

    # Pre-read first frame to determine WxH for encoder
    for packet in container.demux(vstream):
        for frame in packet.decode():
            first_rot = _rotation_degrees_from_frame(frame)
            first_img = _apply_rotation(frame.to_image(), first_rot)
            break
        if first_img is not None:
            break
    if first_img is None:
        container.close()
        raise RuntimeError("Could not decode first frame")

    # Pick target box based on preference and first-frame orientation
    w, h = first_img.size
    if prefer_portrait_box or (h > w):
        target_wh = (480, 640)
    else:
        target_wh = (640, 480)

    # Prepare output MP4
    out = av.open(mp4_path, mode="w")
    stream = out.add_stream("libx264", rate=fps)  # requires libx264
    stream.width, stream.height = target_wh
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": str(crf), "preset": preset, "profile": "baseline"}
    time_base = Fraction(1, fps)

    # Prepare ZIP
    zf = zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)

    # Rewind to decode from start (post-seek)
    if start_time is not None:
        container.seek(int(start_time * av.time_base))

    frame_index = 0
    def process_image(img: Image.Image):
        nonlocal frame_index
        # For ZIP: choose per-frame orientation; portrait stays portrait
        w, h = img.size
        target_this = (480, 640) if h > w else (640, 480)
        img_zip = _resize_image(img, target_wh=target_this, mode="fit")  # preserve orientation, no bars

        # For MP4: constant WxH; letterbox if needed
        img_vid = _resize_image(img, target_wh=target_wh, mode=mode, pad_color=pad_color)

        # Write JPEG into ZIP
        bio = io.BytesIO()
        img_zip.save(bio, format="JPEG", quality=jpeg_quality, optimize=True,
                     progressive=False, subsampling=jpeg_subsampling)
        bio.seek(0)
        zf.writestr(f"frame_{frame_index:06d}.jpg", bio.read())

        # Encode to MP4
        arr = np.asarray(img_vid.convert("RGB"))
        frame_rgb = av.VideoFrame.from_ndarray(arr, format="rgb24")
        frame_rgb.pict_type = "NONE"
        frame_rgb.time_base = time_base
        frame_rgb.pts = frame_index
        # Reformat to yuv420p for encoder
        frame_yuv = frame_rgb.reformat(format="yuv420p", width=target_wh[0], height=target_wh[1])
        for pkt in stream.encode(frame_yuv):
            out.mux(pkt)

        frame_index += 1

    # Main decode loop
    for packet in container.demux(vstream):
        for frame in packet.decode():
            if end_time is not None and frame.time is not None and frame.time > end_time:
                break
            rot = _rotation_degrees_from_frame(frame)
            img = _apply_rotation(frame.to_image(), rot)
            process_image(img)

    # Flush encoder
    for pkt in stream.encode(None):
        out.mux(pkt)

    # Close everything
    zf.close()
    out.close()
    container.close()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser("Downscale → ZIP(JPEGs) + MP4 (H.264) in one pass (PyAV; no shelling).")
    p.add_argument("input")
    p.add_argument("zip_out")
    p.add_argument("mp4_out")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="veryfast")
    p.add_argument("--prefer-portrait", action="store_true",
                   help="Use 480x640 as the fixed encoder box if first frame is portrait or if you prefer portrait.")
    p.add_argument("--mode", choices=["letterbox","fit"], default="letterbox",
                   help="For MP4 only. letterbox keeps constant WxH; fit will FAIL if frames vary (not recommended).")
    p.add_argument("--start", type=float)
    p.add_argument("--end", type=float)
    args = p.parse_args()

    video_to_zip_and_mp4(
        args.input, args.zip_out, args.mp4_out,
        fps=args.fps, crf=args.crf, preset=args.preset,
        prefer_portrait_box=args.prefer_portrait, mode=args.mode,
        start_time=args.start, end_time=args.end
    )
