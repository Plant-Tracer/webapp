from pathlib import Path

import numpy as np
import pytest

from resize_app import movie_glue
from resize_app import tracer
from resize_app.src.app.schema import Trackpoint


ROOT = Path(__file__).resolve().parents[1]


def test_first_frame_to_track_uses_next_frame_after_source():
    assert movie_glue.first_frame_to_track(source_frame_number=0) == 1
    assert movie_glue.first_frame_to_track(source_frame_number=5) == 6


def test_first_frame_to_track_rejects_negative_source_frame():
    with pytest.raises(ValueError):
        movie_glue.first_frame_to_track(source_frame_number=-1)


def test_movie_rotation_defaults_invalid_metadata_to_zero():
    assert movie_glue.movie_rotation({movie_glue.MOVIE_ROTATION: "90"}) == 90
    assert movie_glue.movie_rotation({movie_glue.MOVIE_ROTATION: "unexpected"}) == 0
    assert movie_glue.movie_rotation({movie_glue.MOVIE_ROTATION: None}) == 0
    assert movie_glue.movie_rotation({}) == 0


def test_analysis_frame_height_from_movie_uses_tracer_processed_frame():
    movie_path = ROOT / "tests" / "data" / "2019-07-31 plantmovie.mov"

    assert movie_glue.analysis_frame_height_from_movie(movie_url=str(movie_path), rotation=0) == 480
    assert movie_glue.analysis_frame_height_from_movie(movie_url=str(movie_path), rotation=90) == 640


def test_trace_movie_v2_respects_frame_end(monkeypatch):
    frames = [np.zeros((8, 8, 3), dtype=np.uint8) for _frame_number in range(4)]
    monkeypatch.setattr(tracer, "get_frames_from_url", lambda _movie_url, _rotation: frames)

    def fake_trace_frame(*, gray_frame_prev, gray_frame, trackpoints, frame_number):
        del gray_frame_prev, gray_frame, trackpoints
        return [Trackpoint(x=frame_number, y=frame_number + 1, label="apex", frame_number=frame_number)]

    monkeypatch.setattr(tracer, "cv2_trace_frame", fake_trace_frame)
    callbacks = []

    trackpoints = tracer.trace_movie_v2(
        movie_url="https://example.com/movie.mp4",
        frame_start=1,
        frame_end=2,
        trackpoints=[Trackpoint(x=0, y=1, label="apex", frame_number=0)],
        callback=callbacks.append,
    )

    assert [tp.frame_number for tp in trackpoints] == [0, 1, 2]
    assert [obj.frame_number for obj in callbacks] == [0, 1, 2, 3]
    assert callbacks[2].frame_trackpoints == [Trackpoint(x=2, y=3, label="apex", frame_number=2)]
    assert callbacks[3].frame_trackpoints == []


def test_trace_movie_v2_clips_traced_mp4_to_output_range(monkeypatch):
    frames = []
    for frame_number in range(4):
        frame = np.zeros((12, 12, 3), dtype=np.uint8)
        frame[0, 0] = [frame_number, 0, 0]
        frames.append(frame)
    monkeypatch.setattr(tracer, "get_frames_from_url", lambda _movie_url, _rotation: frames)

    def fake_trace_frame(*, gray_frame_prev, gray_frame, trackpoints, frame_number):
        del gray_frame_prev, gray_frame, trackpoints
        return [Trackpoint(x=6, y=6, label="apex", frame_number=frame_number)]

    appended_frames = []

    class FakeWriter:
        def append_data(self, frame):
            appended_frames.append(frame.copy())

        def close(self):
            pass

    monkeypatch.setattr(tracer, "cv2_trace_frame", fake_trace_frame)
    monkeypatch.setattr(tracer.imageio, "get_writer", lambda *_args, **_kwargs: FakeWriter())

    tracer.trace_movie_v2(
        movie_url="https://example.com/movie.mp4",
        frame_start=1,
        frame_end=2,
        trackpoints=[Trackpoint(x=6, y=6, label="apex", frame_number=0)],
        movie_traced_path=Path("traced.mp4"),
        movie_traced_frame_range=tracer.TracedMovieFrameRange(start=1, end=2),
        callback=None,
    )

    assert len(appended_frames) == 2
    assert [int(frame[0, 0, 2]) for frame in appended_frames] == [1, 2]
