from unittest.mock import Mock, patch

from resize_app import movie_glue


def test_queue_tracing_uses_local_queue_when_configured(monkeypatch):
    monkeypatch.setenv("TRACKING_QUEUE_MODE", "local")

    with patch("resize_app.local_queue.enqueue_message") as enqueue_message:
        result = movie_glue.queue_tracing("test-key", "m123", 7)

    enqueue_message.assert_called_once_with(
        {"api_key": "test-key", "movie_id": "m123", "frame_start": 7}
    )
    assert result["error"] is False


def test_prepare_tracing_request_marks_movie_tracing_before_queueing():
    fake_ddbo = Mock()
    fake_ddbo.movies = "movies-table"

    with patch("resize_app.movie_glue.validate_movie_access", return_value=(fake_ddbo, "u123", {"movie_id": "m123"})), \
         patch("resize_app.movie_glue.clear_movie_tracking_after_frame", return_value=12) as clear_tracking:
        result = movie_glue.prepare_tracing_request(api_key="test-key", movie_id="m123", frame_start=7)

    clear_tracking.assert_called_once_with(movie_id="m123", frame_number=7)
    fake_ddbo.update_table.assert_called_once_with(fake_ddbo.movies, "m123", {movie_glue.MOVIE_STATUS: movie_glue.MOVIE_STATE_TRACING})
    assert result == {"movie_id": "m123", "frame_start": 7, "cleared_frames": 12}
