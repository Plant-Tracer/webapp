from unittest.mock import patch

import pytest

from resize_app import movie_glue
from resize_app import tracer
from resize_app.src.app.odb_movie_data import delete_object
from resize_app.src.app.schema import Trackpoint


def test_queue_tracing_uses_local_queue_when_configured(monkeypatch):
    monkeypatch.setenv("TRACING_QUEUE_MODE", "local")

    with patch("resize_app.local_queue.enqueue_message") as enqueue_message:
        result = movie_glue.queue_tracing("test-key", "m123", 7, 20)

    enqueue_message.assert_called_once_with(
        {
            "job_type": "trace",
            "api_key": "test-key",
            "movie_id": "m123",
            "frame_start": 7,
            "frame_end": 20,
        }
    )
    assert result["error"] is False


def test_prepare_tracing_request_marks_movie_tracing_before_queueing(new_movie):
    ddbo = new_movie["ddbo"]
    movie_id = new_movie[movie_glue.odb.MOVIE_ID]
    ddbo.update_movie(
        movie_id,
        {movie_glue.odb.LAST_ACTIVITY_AT: 1},
        touch_activity=False,
    )

    result = movie_glue.prepare_tracing_request(
        api_key=new_movie[movie_glue.odb.API_KEY],
        movie_id=movie_id,
        frame_start=7,
        frame_end=20,
    )

    movie = ddbo.get_movie(movie_id)
    assert movie[movie_glue.MOVIE_STATUS] == movie_glue.odb.MOVIE_STATE_TRACING
    assert movie[movie_glue.odb.LAST_ACTIVITY_AT] > 1
    assert result["movie_id"] == movie_id
    assert result["frame_start"] == 7
    assert result["frame_end"] == 20
    assert result["cleared_frames"] == 0
    assert result["job_id"]
    lock = ddbo.get_active_movie_trace_lock(movie_id)
    assert lock and lock.job_id == result["job_id"]


def test_prepare_tracing_request_rejects_second_active_lock(new_movie):
    movie_id = new_movie[movie_glue.odb.MOVIE_ID]
    kwargs = {
        "api_key": new_movie[movie_glue.odb.API_KEY],
        "movie_id": movie_id,
        "frame_start": 0,
    }
    movie_glue.prepare_tracing_request(**kwargs)

    with pytest.raises(movie_glue.odb.MovieTracingLocked):
        movie_glue.prepare_tracing_request(**kwargs)


def test_run_tracing_passes_frame_end_and_ignores_callback_frames_after_end(new_movie):
    ddbo = new_movie["ddbo"]
    movie_id = new_movie[movie_glue.odb.MOVIE_ID]
    ddbo.update_movie(
        movie_id,
        {
            movie_glue.TOTAL_FRAMES: 5,
            movie_glue.odb.TRIM_START_FRAME: 0,
            movie_glue.odb.TRIM_END_FRAME: 4,
            movie_glue.odb.LAST_ACTIVITY_AT: 1,
        },
        touch_activity=False,
    )
    for frame_number in range(3):
        movie_glue.put_frame_trackpoints(
            movie_id=movie_id,
            frame_number=frame_number,
            trackpoints=[
                Trackpoint(
                    x=10 + frame_number,
                    y=20 + frame_number,
                    label="apex",
                    frame_number=frame_number,
                )
            ],
        )
    ddbo.update_movie(
        movie_id,
        {movie_glue.odb.LAST_ACTIVITY_AT: 1},
        touch_activity=False,
    )

    def trace_movie_side_effect(**kwargs):
        assert kwargs["frame_start"] == 2
        assert kwargs["frame_end"] == 3
        assert kwargs["movie_traced_frame_range"] == tracer.TracedMovieFrameRange(start=0, end=3)
        callback = kwargs["callback"]
        callback(tracer.TracerCallbackArg(
            frame_number=3,
            frame_data=None,
            frame_trackpoints=[Trackpoint(x=13, y=23, label="apex", frame_number=3)],
        ))
        callback(tracer.TracerCallbackArg(
            frame_number=4,
            frame_data=None,
            frame_trackpoints=[Trackpoint(x=14, y=24, label="apex", frame_number=4)],
        ))
        kwargs["movie_zipfile_path"].write_bytes(b"test zip")
        kwargs["movie_traced_path"].write_bytes(b"test mp4")
        return [
            Trackpoint(x=10, y=20, label="apex", frame_number=1),
            Trackpoint(x=13, y=23, label="apex", frame_number=3),
        ]

    with patch(
        "resize_app.movie_glue.tracer.trace_movie_v2",
        side_effect=trace_movie_side_effect,
    ):
        movie_glue.run_tracing(movie_id=movie_id, frame_start=1, frame_end=3)

    movie = ddbo.get_movie(movie_id)
    try:
        assert movie[movie_glue.LAST_FRAME_TRACKED] == 3
        assert movie[movie_glue.TOTAL_FRAMES] == 5
        assert movie[movie_glue.MOVIE_STATUS] == movie_glue.MOVIE_STATE_TRACING_COMPLETED
        assert movie[movie_glue.NEEDS_RETRACING] == 0
        assert movie[movie_glue.MOVIE_TRACED_URN].endswith("_traced.mov")
        assert movie[movie_glue.MOVIE_ZIPFILE_URN].endswith("_zipfile.mov")
        assert movie[movie_glue.odb.LAST_ACTIVITY_AT] > 1
        assert "trackpoints" not in ddbo.get_movie_frame(movie_id, 2)
        frame_three = movie_glue.get_movie_trackpoints(
            movie_id=movie_id,
            frame_start=3,
            frame_end=3,
        )
        assert frame_three[0]["label"] == "apex"
    finally:
        delete_object(movie[movie_glue.MOVIE_TRACED_URN])
