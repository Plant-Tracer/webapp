#!/usr/bin/env python3
"""
video.py - routines to resize video and pack/unpack video from jpegs

Pure Python: uses PyAV (libav*), Pillow; no subprocess calls to ffmpeg.
"""

import io
import zipfile
from pathlib import Path
from typing import Tuple, Optional
import argparse
from fractions import Fraction

import av
import numpy as np
from PIL import Image, ImageOps  # pip install pillow

DEFAULT_JPEG_QUALITY = 70

# ---------- Geometry & rotation helpers ----------

def _rotation_degrees_from_frame(frame: av.video.frame.VideoFrame) -> int:
    """
    Extract clockwise rotation (0/90/180/270) from frame side data if present.
    Falls back to stream 'rotate' metadata if available.
    """
    # Newer FFmpeg writes a display matrix in side data.
    for sd in frame.side_data:
        if sd.type.name == "DISPLAYMATRIX":
            # Matrix maps frame to display; angle is derived as per FFmpeg
            # PyAV exposes .to_dict() -> {'rotation': 90.0} in recent builds.
            d = sd.to_dict()
            if "rotation" in d:
                rot = int(round(d["rotation"])) % 360
                return (rot + 360) % 360

    return 0


def _apply_rotation(img: Image.Image, degrees: int) -> Image.Image:
    if degrees % 360 == 0:
        return img
    # PIL rotates counter-clockwise for ROTATE_* transposes
    m = {90: Image.Transpose.ROTATE_270,
         180: Image.Transpose.ROTATE_180,
         270: Image.Transpose.ROTATE_90}
    return img.transpose(m.get(degrees % 360, Image.Transpose.ROTATE_270))


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
    match (mode):
        case ("fit"):
            nw, nh = _compute_fit_size(img.size, target_wh)
            if (nw, nh) == img.size:
                return img
            img.resize((nw, nh), resample=resample)
            return img
        case ("letterbox"):
            return ImageOps.pad(img, target_wh, method=resample, color=pad_color)
        case ("_"):
            raise ValueError("mode must be 'fit' or 'letterbox'")


# ---------- Main processing ----------

# pylint: disable=too-many-locals, disable=too-many-arguments,disable=too-many-branches,disable=too-many-statements
def video_unpack_resize( *,
                         infile_path: Path,
                         outfile_path: Path|None = None, # output
                         zipfile_path: Path|None = None, # output
                         frame0_path: Path|None = None, # output
                         jpeg_quality: int = DEFAULT_JPEG_QUALITY,
                         jpeg_subsampling: str = "4:2:0",
                         fps: int = 30,
                         prefer_portrait_box: bool = False,   # False => 640x480, True => 480x640
                         mode: str = "letterbox",             # encoder needs constant WxH; use letterbox
                         start_time: Optional[float] = None,
                         end_time: Optional[float] = None,
                         pad_color=(0,0,0),
                         crf: int = 20,
                         preset: str = "veryfast" ):
    """
    One pass: decode -> rotate -> downscale -> write JPEGs to ZIP + frames to MP4 (H.264).
    Requires PyAV linked with libx264. No shelling to ffmpeg.
    """
    print("video_unpack_resize",infile_path,outfile_path,zipfile_path,frame0_path)
    infile_container = av.open(infile_path)
    vstreams = [s for s in infile_container.streams if s.type == "video"]
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
        infile_container.seek(int(start_time * av.time_base))

    # Pre-read first frame to determine WxH for encoder
    for packet in infile_container.demux(vstream):
        for frame in packet.decode():
            first_rot = _rotation_degrees_from_frame(frame)
            first_img = _apply_rotation(frame.to_image(), first_rot)
            break
        if first_img is not None:
            break
    if first_img is None:
        infile_container.close()
        raise RuntimeError("Could not decode first frame")

    # Pick target box based on preference and first-frame orientation
    w, h = first_img.size
    if prefer_portrait_box or (h > w):
        target_wh = (480, 640)
    else:
        target_wh = (640, 480)

    # Prepare output MP4
    if outfile_path is not None:
        out = av.open(outfile_path, mode="w")
        print("open ",outfile_path," for out")
        stream = out.add_stream("libx264", rate=fps)  # requires libx264
        stream.width, stream.height = target_wh
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": str(crf), "preset": preset, "profile": "baseline"}
    else:
        out = None
        stream = None

    time_base = Fraction(1, fps)

    # Prepare ZIP
    if zipfile_path is not None:
        # pylint: disable=consider-using-with
        zf = zipfile.ZipFile(str(zipfile_path), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
    else:
        zf = None

    # Rewind to decode from start (post-seek)
    if start_time is not None:
        infile_container.seek(int(start_time * av.time_base))

    frame_index = 0
    def process_image(img: Image.Image):
        nonlocal frame_index

        # For ZIP: choose per-frame orientation; portrait stays portrait
        # w, h = img.size; target_this = (480, 640) if h > w else (640, 480)
        # For MP4: constant WxH; letterbox if needed
        img_vid = _resize_image(img, target_wh=target_wh, mode=mode, pad_color=pad_color)

        # Write JPEG into ZIP
        bio = io.BytesIO()
        img_vid.save(bio, format="JPEG", quality=jpeg_quality, optimize=True,
                     progressive=False, subsampling=jpeg_subsampling)
        bio.seek(0)
        if zf is not None:
            zf.writestr(f"frame_{frame_index:06d}.jpg", bio.read())

        # Save frame0?
        if (frame_index==0) and (frame0_path is not None):
            bio.seek(0)
            frame0_path.write_bytes(bio.read())

        # Encode to MP4
        arr = np.asarray(img_vid.convert("RGB"))
        frame_rgb = av.VideoFrame.from_ndarray(arr, format="rgb24")
        #frame_rgb.pict_type = "NONE"
        frame_rgb.time_base = time_base
        frame_rgb.pts = frame_index
        # Reformat to yuv420p for encoder
        frame_yuv = frame_rgb.reformat(format="yuv420p", width=target_wh[0], height=target_wh[1])
        for pkt in stream.encode(frame_yuv):
            out.mux(pkt)

        frame_index += 1

    # Main decode loop
    def process_container():
        for packet in infile_container.demux(vstream):
            for frame in packet.decode():
                if end_time is not None and frame.time is not None and frame.time > end_time:
                    return
                rot = _rotation_degrees_from_frame(frame)
                img = _apply_rotation(frame.to_image(), rot)
                process_image(img)
                # only looking for first frame?
                if frame_index>0 and zf is None:
                    return


    process_container()

    if zf is not None:
        zf.close()

    if (out is not None) and (stream is not None):
        for pkt in stream.encode(None):
            out.mux(pkt)
        print("********** CLOSE out *************")
        out.close()

    infile_container.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser("Downscale → ZIP(JPEGs) + MP4 (H.264) in one pass (PyAV; no shelling).")
    p.add_argument("infile")
    p.add_argument("outfile")
    p.add_argument("zipfile_out")
    p.add_argument("frame0")
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

    video_unpack_resize(
        infile_path = Path(args.infile),
        zipfile_path = Path(args.zipfile_out),
        outfile_path = Path(args.outfile),
        frame0_path = Path(args.frame0),
        fps=args.fps, crf=args.crf, preset=args.preset,
        prefer_portrait_box=args.prefer_portrait, mode=args.mode,
        start_time=args.start, end_time=args.end
    )
