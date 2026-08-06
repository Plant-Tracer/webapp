"""Create the MP4 derivative used for Plant Tracer frame analysis."""

# pylint: disable=no-member

import json
import shutil
from pathlib import Path

import cv2
import imageio
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_ANALYSIS_WIDTH = 640
DEFAULT_ANALYSIS_HEIGHT = 480
DEFAULT_ANALYSIS_FPS = 15.0
ANALYSIS_PLAYER_FILENAME = "index.html"
ANALYSIS_PLAYER_LIBRARY_FILENAME = "mp4box.all.js"
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
    return Path(__file__).resolve().parents[3]


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


def encode_analysis_mp4(*, source_path: Path, output_path: Path, options: AnalysisMp4Options) -> AnalysisMp4Result:
    """Encode one rotated, scaled, frame-numbered analysis MP4."""
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"cannot open MP4: {source_path}")
    fps = DEFAULT_ANALYSIS_FPS
    frame_count = 0
    width = 0
    height = 0
    writer = None
    try:
        writer = imageio.get_writer(
            output_path,
            format="FFMPEG",
            mode="I",
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=None,
            output_params=[
                *H264_OUTPUT_PARAMETERS,
                "-metadata", "comment=PlantTracer analysis MP4",
            ],
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


def copy_player_bundle(*, bundle_dir: Path, movie_name: str) -> Path:
    """Copy the WebCodecs player and its local MP4 demuxer into a bundle."""
    root = project_root()
    player_source = root / "src/app/static/mp4player-demo3.html"
    library_source = root / "node_modules/mp4box/dist/mp4box.all.js"
    if not library_source.is_file():
        raise FileNotFoundError("mp4box dependency is missing; run npm install")
    player_text = player_source.read_text(encoding="utf-8")
    player_text = player_text.replace(
        "https://cdn.jsdelivr.net/npm/mp4box@2.3.0/dist/mp4box.all.js",
        f"./{ANALYSIS_PLAYER_LIBRARY_FILENAME}",
    )
    player_text = player_text.replace(
        "https://simson.net/plantmovie.mp4",
        f"./{movie_name}",
    )
    player_path = bundle_dir / ANALYSIS_PLAYER_FILENAME
    player_path.write_text(player_text, encoding="utf-8")
    shutil.copyfile(library_source, bundle_dir / ANALYSIS_PLAYER_LIBRARY_FILENAME)
    (bundle_dir / "README.txt").write_text(
        "Serve this directory over HTTP or HTTPS, then open index.html.\n"
        "For a local check: python3 -m http.server --directory .\n"
        "Copy the complete directory to a static web server with scp.\n",
        encoding="utf-8",
    )
    return player_path


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
