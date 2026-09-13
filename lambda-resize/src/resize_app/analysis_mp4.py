"""Create the MP4 derivative used for Plant Tracer frame analysis."""

# pylint: disable=no-member

import json
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .video_writer import H264Writer

DEFAULT_ANALYSIS_WIDTH = 640
DEFAULT_ANALYSIS_HEIGHT = 640
DEFAULT_ANALYSIS_FPS = 15.0
ANALYSIS_PLAYER_FILENAME = "index.html"
ANALYSIS_PLAYER_LIBRARY_FILENAME = "mp4box.all.js"
ANALYSIS_PLAYER_LIBRARY_DEPENDENCIES = (
    "rolldown-runtime-w6R9maHv.mjs",
    "styp-9TIZZDLN.mjs",
)
ANALYSIS_MANIFEST_FILENAME = "analysis-mp4.json"
H264_OUTPUT_PARAMETERS = (
    "-profile:v", "baseline",
    "-level:v", "3.0",
    "-bf", "0",
    "-g", "30",
    "-crf", "18",
    "-movflags", "+faststart",
)


class AnalysisMp4Options(BaseModel):
    """Stable settings shared by the CLI and Lambda upload derivative job."""

    model_config = ConfigDict(frozen=True)

    rotation: int = 0
    max_width: int = Field(default=DEFAULT_ANALYSIS_WIDTH, gt=0)
    max_height: int = Field(default=DEFAULT_ANALYSIS_HEIGHT, gt=0)

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, value: int) -> int:
        """Only accept the UI rotation values."""
        if value not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180, or 270")
        return value


class AnalysisMp4Result(BaseModel):
    """Published analysis bundle details."""

    model_config = ConfigDict(frozen=True)

    bundle_dir: Path
    movie_path: Path
    player_path: Path
    frame_count: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    rotation: int
    encoder: str = "libx264"
    pixel_format: str = "yuv420p"
    profile: str = "baseline"
    b_frames: int = 0


def project_root() -> Path:
    """Return the repository root from the Lambda package source."""
    source_directory = Path(__file__).resolve().parent
    return source_directory.parents[2]


def scaled_movie_name(source_path: Path) -> str:
    """Name the analysis derivative after its source movie."""
    return f"{source_path.stem}_scaled.mp4"


def rotate_frame(frame: np.ndarray, rotation: int) -> np.ndarray:
    """Apply Plant Tracer's clockwise rotation convention."""
    if rotation == 0:
        return frame
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    raise ValueError("rotation must be 0, 90, 180, or 270")


def dimensions_to_fit(*, width: int, height: int, max_width: int, max_height: int) -> tuple[int, int]:
    """Fit a frame inside the analysis rectangle without enlarging it."""
    scale = min(1.0, max_width / width, max_height / height)
    scaled_width = max(2, int(round(width * scale)) // 2 * 2)
    scaled_height = max(2, int(round(height * scale)) // 2 * 2)
    return scaled_width, scaled_height


def scale_frame(frame: np.ndarray, options: AnalysisMp4Options) -> np.ndarray:
    """Resize a frame for yuv420p encoding while preserving aspect ratio."""
    height, width = frame.shape[:2]
    scaled_width, scaled_height = dimensions_to_fit(
        width=width,
        height=height,
        max_width=options.max_width,
        max_height=options.max_height,
    )
    if (scaled_width, scaled_height) == (width, height):
        return frame
    return cv2.resize(frame, (scaled_width, scaled_height), interpolation=cv2.INTER_AREA)


def unlabelled_analysis_frames(source_url: str, options: AnalysisMp4Options):
    """Render source frames in the same geometry, without permanent playback labels."""
    capture = cv2.VideoCapture(source_url)
    try:
        if not capture.isOpened():
            raise ValueError("Cannot open source for traced movie rendering")
        while True:
            success, frame = capture.read()
            if not success:
                return
            yield scale_frame(rotate_frame(frame, options.rotation), options)
    finally:
        capture.release()


def burn_frame_number(frame: np.ndarray, frame_number: int) -> np.ndarray:
    """Burn a one-based frame number into an analysis frame."""
    labelled = frame.copy()
    text = str(frame_number)
    text_face = cv2.FONT_HERSHEY_DUPLEX
    text_scale = 0.75
    text_thickness = 2
    margin = 5
    text_size, _ = cv2.getTextSize(text, text_face, text_scale, text_thickness)
    origin = (labelled.shape[1] - text_size[0] - margin, text_size[1] + margin)
    cv2.rectangle(labelled, origin, (origin[0] + text_size[0], origin[1] - text_size[1]), (0, 0, 255), -1)
    cv2.putText(labelled, text, origin, text_face, text_scale, (255, 255, 255), text_thickness, cv2.LINE_4)
    return labelled


def encode_analysis_mp4(*, source_path: Path, output_path: Path, options: AnalysisMp4Options,
                        comment: str = "PlantTracer analysis MP4") -> AnalysisMp4Result:
    """Encode one rotated, scaled, frame-numbered analysis MP4."""
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"cannot open MP4: {source_path}")
    expected_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = DEFAULT_ANALYSIS_FPS
    frame_count = 0
    width = 0
    height = 0
    writer = None
    try:
        writer = H264Writer(
            output_path,
            fps=fps,
            output_params=[
                *H264_OUTPUT_PARAMETERS,
                "-metadata", f"comment={comment}",
            ],
            quality=None,
        )
        while True:
            success, frame = capture.read()
            if not success or frame is None:
                break
            frame = scale_frame(rotate_frame(frame, options.rotation), options)
            frame_count += 1
            labelled = burn_frame_number(frame, frame_count)
            writer.append_data(cv2.cvtColor(labelled, cv2.COLOR_BGR2RGB))
            height, width = labelled.shape[:2]
    finally:
        capture.release()
        if writer is not None:
            writer.close()
    if frame_count == 0:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"MP4 has no decodable frames: {source_path}")
    if expected_count > 0 and frame_count != expected_count:
        output_path.unlink(missing_ok=True)
        raise ValueError(f"Decoded {frame_count} of {expected_count} source frames")
    validate_encoded_movie(output_path, frame_count=frame_count, width=width, height=height)
    return AnalysisMp4Result(
        bundle_dir=output_path.parent,
        movie_path=output_path,
        player_path=output_path.parent / ANALYSIS_PLAYER_FILENAME,
        frame_count=frame_count,
        width=width,
        height=height,
        fps=fps,
        rotation=options.rotation,
    )


def validate_encoded_movie(path: Path, *, frame_count: int, width: int, height: int) -> None:
    """Decode the completed artifact and verify its frame count and H.264 contract."""
    description = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, check=False,
    ).stderr
    if not all(value in description for value in ("h264", "Baseline", "yuv420p", "15 fps")):
        raise ValueError("Analysis MP4 does not satisfy the H.264 baseline/yuv420p/15 fps contract")
    capture = cv2.VideoCapture(str(path))
    count = 0
    try:
        while True:
            success, frame = capture.read()
            if not success:
                break
            if frame.shape[:2] != (height, width):
                raise ValueError("Analysis MP4 dimensions changed during encoding")
            count += 1
    finally:
        capture.release()
    if count != frame_count:
        raise ValueError(f"Analysis MP4 retained {count} of {frame_count} frames")


def copy_player_bundle(*, bundle_dir: Path, movie_name: str) -> Path:
    """Copy the WebCodecs player and its local MP4 demuxer into a bundle."""
    root = project_root()
    player_source = root / "src/app/static/mp4player-demo3.html"
    player_text = player_source.read_text(encoding="utf-8")
    player_text = player_text.replace(
        "https://simson.net/plantmovie.mp4",
        f"./{movie_name}",
    )
    player_path = bundle_dir / ANALYSIS_PLAYER_FILENAME
    player_path.write_text(player_text, encoding="utf-8")
    for filename in (ANALYSIS_PLAYER_LIBRARY_FILENAME, *ANALYSIS_PLAYER_LIBRARY_DEPENDENCIES):
        source = require_file(
            root / "src/app/static" / filename,
            missing_message=f"the vendored mp4box browser module {filename} is missing",
        )
        shutil.copyfile(source, bundle_dir / filename)
    (bundle_dir / "README.txt").write_text(
        "Serve this directory over HTTP or HTTPS, then open index.html.\n"
        "For a local check: python3 -m http.server --directory .\n"
        "Copy the complete directory to a static web server with scp.\n",
        encoding="utf-8",
    )
    return player_path


def require_file(path: Path, *, missing_message: str) -> Path:
    """Return a required bundle asset or fail with an actionable message."""
    if not path.is_file():
        raise FileNotFoundError(missing_message)
    return path


def create_analysis_bundle(*, source_path: Path, output_dir: Path, options: AnalysisMp4Options) -> AnalysisMp4Result:
    """Atomically create a portable analysis MP4 and WebCodecs player bundle."""
    source_path = source_path.resolve()
    output_dir = output_dir.resolve()
    if not source_path.is_file():
        raise ValueError(f"input MP4 does not exist: {source_path}")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    partial_dir = output_dir.with_name(f".{output_dir.name}.partial")
    if partial_dir.exists():
        raise FileExistsError(f"temporary output directory already exists: {partial_dir}")
    partial_dir.mkdir(parents=True)
    try:
        movie_path = partial_dir / scaled_movie_name(source_path)
        result = encode_analysis_mp4(source_path=source_path, output_path=movie_path, options=options)
        player_path = copy_player_bundle(bundle_dir=partial_dir, movie_name=movie_path.name)
        result = result.model_copy(update={"player_path": player_path})
        result = result.model_copy(
            update={
                "bundle_dir": output_dir,
                "movie_path": output_dir / movie_path.name,
                "player_path": output_dir / player_path.name,
            }
        )
        (partial_dir / ANALYSIS_MANIFEST_FILENAME).write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        partial_dir.replace(output_dir)
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    return result
