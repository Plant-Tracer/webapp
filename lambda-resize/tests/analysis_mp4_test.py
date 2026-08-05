"""Tests for the shared analysis-MP4 encoder and its command-line entry point."""

# pylint: disable=no-member

from pathlib import Path
import subprocess

import cv2
import imageio_ffmpeg
import numpy as np
import pytest

from resize_app import analysis_mp4, analysis_mp4_cli
from tests.fixtures.analysis_mp4_fixture import write_four_color_movie


def ffmpeg_description(path: Path) -> str:
    """Return the installed ImageIO FFmpeg stream description."""
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stderr


def test_cli_uses_shared_encoder_and_creates_portable_bundle(tmp_path, capsys):
    """The CLI creates an atomic local-player bundle through the shared service."""
    source_path = tmp_path / "source.mp4"
    output_dir = tmp_path / "player"
    write_four_color_movie(source_path, fps=8)

    assert analysis_mp4_cli.create_analysis_bundle is analysis_mp4.create_analysis_bundle
    assert analysis_mp4_cli.main([
        str(source_path), str(output_dir), "--rotation", "90", "--max-width", "64", "--max-height", "48",
    ]) == 0

    result_text = capsys.readouterr().out
    movie_path = output_dir / "source_scaled.mp4"
    assert movie_path.is_file()
    assert (output_dir / "index.html").is_file()
    assert (output_dir / "mp4box.all.js").is_file()
    assert (output_dir / "analysis-mp4.json").is_file()
    assert "source_scaled.mp4" in result_text
    assert "cdn.jsdelivr.net" not in (output_dir / "index.html").read_text(encoding="utf-8")
    assert "./source_scaled.mp4" in (output_dir / "index.html").read_text(encoding="utf-8")

    metadata = analysis_mp4.AnalysisMp4Result.model_validate_json(
        (output_dir / "analysis-mp4.json").read_text(encoding="utf-8")
    )
    assert metadata.frame_count == 4
    assert metadata.bundle_dir == output_dir
    assert metadata.movie_path == output_dir / "source_scaled.mp4"
    assert metadata.player_path == output_dir / "index.html"
    assert (metadata.width, metadata.height) == (24, 48)
    assert metadata.rotation == 90
    assert metadata.b_frames == 0
    assert metadata.fps == analysis_mp4.DEFAULT_ANALYSIS_FPS

    capture = cv2.VideoCapture(str(movie_path))
    try:
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 4
        success, first_frame = capture.read()
    finally:
        capture.release()
    assert success
    assert first_frame is not None
    assert first_frame.shape[:2] == (48, 24)
    assert np.any(np.all(first_frame[:20, -20:] >= 140, axis=2))

    stream_description = ffmpeg_description(movie_path)
    assert "h264" in stream_description
    assert "yuv420p" in stream_description
    assert "Baseline" in stream_description


def test_invalid_input_leaves_no_published_bundle(tmp_path):
    """Invalid input must leave neither a final nor temporary output directory."""
    output_dir = tmp_path / "player"
    with pytest.raises(ValueError, match="does not exist"):
        analysis_mp4.create_analysis_bundle(
            source_path=tmp_path / "missing.mp4",
            output_dir=output_dir,
            options=analysis_mp4.AnalysisMp4Options(),
        )
    assert not output_dir.exists()
    assert not (tmp_path / ".player.partial").exists()
