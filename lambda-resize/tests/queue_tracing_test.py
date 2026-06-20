from unittest.mock import Mock, patch

from resize_app import movie_glue
from resize_app import tracer
from resize_app.src.app.schema import Trackpoint


def test_queue_tracing_uses_local_queue_when_configured(monkeypatch):
    monkeypatch.setenv("TRACING_QUEUE_MODE", "local")

    with patch("resize_app.local_queue.enqueue_message") as enqueue_message:
        result = movie_glue.queue_tracing("test-key", "m123", 7, 20)

    enqueue_message.assert_called_once_with(
        {"api_key": "test-key", "movie_id": "m123", "frame_start": 7, "frame_end": 20}
    )
    assert result["error"] is False


def test_prepare_tracing_request_marks_movie_tracing_before_queueing():
    fake_ddbo = Mock()
    fake_ddbo.movies = "movies-table"

    with patch("resize_app.movie_glue.validate_movie_access", return_value=(fake_ddbo, "u123", {"movie_id": "m123"})), \
         patch("resize_app.movie_glue.clear_movie_tracking_after_frame", return_value=12) as clear_tracking:
        result = movie_glue.prepare_tracing_request(api_key="test-key", movie_id="m123", frame_start=7, frame_end=20)

    clear_tracking.assert_called_once_with(movie_id="m123", frame_number=7, frame_end=20)
    fake_ddbo.update_table.assert_called_once_with(fake_ddbo.movies, "m123", {movie_glue.MOVIE_STATUS: movie_glue.MOVIE_STATE_TRACING})
    assert result == {"movie_id": "m123", "frame_start": 7, "frame_end": 20, "cleared_frames": 12}


def test_run_tracing_passes_frame_end_and_ignores_callback_frames_after_end():
    fake_ddbo = Mock()
    fake_ddbo.movies = "movies-table"
    movie_record = {
        movie_glue.MOVIE_DATA_URN: "s3://bucket/movie.mp4",
        movie_glue.TOTAL_FRAMES: 5,
        movie_glue.MOVIE_ROTATION: 0,
    }
    seed_trackpoints = [Trackpoint(x=10, y=20, label="apex", frame_number=1)]

    def trace_movie_side_effect(**kwargs):
        assert kwargs["frame_start"] == 2
        assert kwargs["frame_end"] == 3
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
        return [
            Trackpoint(x=10, y=20, label="apex", frame_number=1),
            Trackpoint(x=13, y=23, label="apex", frame_number=3),
        ]

    with patch("resize_app.movie_glue.DDBO", return_value=fake_ddbo), \
         patch("resize_app.movie_glue.clear_movie_tracking_after_frame", return_value=1) as clear_tracking, \
         patch("resize_app.movie_glue.get_movie_metadata", return_value=movie_record), \
         patch("resize_app.movie_glue.s3_presigned.make_signed_url", return_value="https://example.com/movie.mp4"), \
         patch("resize_app.movie_glue.analysis_frame_height_from_movie", return_value=100), \
         patch("resize_app.movie_glue.odb.ensure_bottom_left_trackpoints"), \
         patch("resize_app.movie_glue.get_movie_trackpoints", return_value=[tp.model_dump() for tp in seed_trackpoints]), \
         patch("resize_app.movie_glue.odb.flip_trackpoints_y", side_effect=lambda trackpoints, _height: trackpoints), \
         patch("resize_app.movie_glue.mp4_metadata_lib.build_comment", return_value="comment"), \
         patch("resize_app.movie_glue.tracer.trace_movie_v2", side_effect=trace_movie_side_effect), \
         patch("resize_app.movie_glue.write_object_from_path"), \
         patch("resize_app.movie_glue.put_frame_trackpoints") as put_frame_trackpoints:
        movie_glue.run_tracing(movie_id="m123", frame_start=1, frame_end=3)

    clear_tracking.assert_called_once_with(movie_id="m123", frame_number=1, frame_end=3)
    put_frame_trackpoints.assert_called_once_with(
        movie_id="m123",
        frame_number=3,
        trackpoints=[Trackpoint(x=13, y=23, label="apex", frame_number=3)],
    )
    fake_ddbo.update_table.assert_any_call(
        fake_ddbo.movies,
        "m123",
        {movie_glue.LAST_FRAME_TRACKED: 3},
    )
    fake_ddbo.update_table.assert_any_call(
        fake_ddbo.movies,
        "m123",
        {
            movie_glue.TOTAL_FRAMES: 5,
            movie_glue.MOVIE_STATUS: movie_glue.MOVIE_STATE_TRACING_COMPLETED,
            movie_glue.MOVIE_TRACED_URN: "s3://bucket/movie_traced.mp4",
            movie_glue.MOVIE_ZIPFILE_URN: "s3://bucket/movie_zipfile.mp4",
        },
    )
