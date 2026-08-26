"""Smoke-test the built lambda-resize ARM64 media stack inside its build container."""

import argparse
import importlib
import os
from pathlib import Path
import sys
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.artifact))

    cv2 = importlib.import_module("cv2")
    imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
    np = importlib.import_module("numpy")

    executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not os.access(executable, os.X_OK):
        raise RuntimeError(f"packaged FFmpeg is not executable: {executable}")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "smoke.mp4"
        writer = imageio_ffmpeg.write_frames(
            output_path,
            (32, 24),
            pix_fmt_in="rgb24",
            pix_fmt_out="yuv420p",
            fps=15,
            codec="libx264",
            macro_block_size=1,
        )
        writer.send(None)
        writer.send(np.zeros((24, 32, 3), dtype=np.uint8))
        writer.close()
        capture = cv2.VideoCapture(str(output_path))
        try:
            success, frame = capture.read()
        finally:
            capture.release()
        if not success or frame is None or frame.shape[:2] != (24, 32):
            raise RuntimeError("OpenCV could not decode the packaged FFmpeg output")
    print(f"lambda-resize artifact media smoke passed: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
