from pathlib import Path

import pytest

from resize_app import movie_glue


ROOT = Path(__file__).resolve().parents[1]


def test_first_frame_to_track_uses_next_frame_after_source():
    assert movie_glue.first_frame_to_track(source_frame_number=0) == 1
    assert movie_glue.first_frame_to_track(source_frame_number=5) == 6


def test_first_frame_to_track_rejects_negative_source_frame():
    with pytest.raises(ValueError):
        movie_glue.first_frame_to_track(source_frame_number=-1)


def test_analysis_frame_height_from_movie_uses_tracker_processed_frame():
    movie_path = ROOT / "tests" / "data" / "2019-07-31 plantmovie.mov"

    assert movie_glue.analysis_frame_height_from_movie(movie_url=str(movie_path), rotation=0) == 480
    assert movie_glue.analysis_frame_height_from_movie(movie_url=str(movie_path), rotation=90) == 640
