import pytest

from resize_app import movie_glue


def test_first_frame_to_track_uses_next_frame_after_source():
    assert movie_glue.first_frame_to_track(source_frame_number=0) == 1
    assert movie_glue.first_frame_to_track(source_frame_number=5) == 6


def test_first_frame_to_track_rejects_negative_source_frame():
    with pytest.raises(ValueError):
        movie_glue.first_frame_to_track(source_frame_number=-1)
