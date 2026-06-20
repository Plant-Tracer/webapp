import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from resize_app import lambda_tracing_handler


def test_process_tracing_message_passes_frame_end_to_runner():
    with patch("resize_app.lambda_tracing_handler.movie_glue.run_tracing") as run_tracing:
        lambda_tracing_handler.process_tracing_message({
            "movie_id": "m123",
            "frame_start": "7",
            "frame_end": "20",
        })

    run_tracing.assert_called_once_with(movie_id="m123", frame_start=7, frame_end=20)


def test_process_tracing_message_rejects_missing_movie_id():
    with pytest.raises(ValueError, match="movie_id is required"):
        lambda_tracing_handler.process_tracing_message({"frame_start": 7})


def test_process_tracing_record_decodes_json_body():
    record = SimpleNamespace(body=json.dumps({"movie_id": "m123", "frame_start": 7}))
    with patch("resize_app.lambda_tracing_handler.process_tracing_message") as process:
        lambda_tracing_handler.process_tracing_record(record)

    process.assert_called_once_with({"movie_id": "m123", "frame_start": 7})


def test_process_tracing_record_rejects_invalid_json():
    record = SimpleNamespace(body="{not-json")

    with pytest.raises(json.JSONDecodeError):
        lambda_tracing_handler.process_tracing_record(record)
