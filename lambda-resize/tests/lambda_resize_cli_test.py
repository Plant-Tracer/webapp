"""Tests for the lambda-resize developer diagnostics CLI."""

from types import SimpleNamespace

from lambda_resize_cli import (
    TEST_FILE,
    build_parser,
    extract_first_frame,
    make_jpeg,
    trace_movie,
)


def test_make_jpeg_writes_a_real_jpeg(tmp_path):
    """The JPEG diagnostic writes a decodable JPEG artifact."""
    output = tmp_path / "test.jpg"
    make_jpeg(SimpleNamespace(output=output, rotate=90))
    assert output.read_bytes().startswith(b"\xff\xd8")


def test_extract_first_frame_reads_the_repository_test_movie(tmp_path):
    """The first-frame diagnostic exercises the real local movie path."""
    output = tmp_path / "first-frame.jpg"
    extract_first_frame(SimpleNamespace(input=str(TEST_FILE), output=output, rotate=0))
    jpeg = output.read_bytes()
    assert jpeg.startswith(b"\xff\xd8")
    assert b"test comment" in jpeg


def test_parser_preserves_tracer_diagnostic_contract(tmp_path):
    """The renamed CLI retains explicit tracer artifact arguments."""
    traced = tmp_path / "traced.mp4"
    archive = tmp_path / "frames.zip"
    args = build_parser().parse_args([
        "tracer",
        "--movie-traced", str(traced),
        "--zipfile", str(archive),
        "--rotate", "180",
    ])
    assert args.func is trace_movie
    assert args.movie_traced == traced
    assert args.zipfile == archive
    assert args.rotate == 180
