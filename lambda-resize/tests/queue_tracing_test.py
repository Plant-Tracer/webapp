from unittest.mock import patch

from resize_app import movie_glue


def test_queue_tracing_uses_local_queue_when_configured(monkeypatch):
    monkeypatch.setenv("TRACKING_QUEUE_MODE", "local")

    with patch("resize_app.local_queue.enqueue_message") as enqueue_message:
        result = movie_glue.queue_tracing("test-key", "m123", 7)

    enqueue_message.assert_called_once_with(
        {"api_key": "test-key", "movie_id": "m123", "frame_start": 7}
    )
    assert result["error"] is False
