from unittest.mock import patch

import pytest

from resize_app import async_work
from resize_app import lambda_tracing_handler
from resize_app.src.app.constants import C


def test_process_tracing_message_passes_frame_end_to_runner():
    with patch("resize_app.lambda_tracing_handler.movie_glue.run_tracing") as run_tracing:
        lambda_tracing_handler.process_tracing_message({
            "movie_id": "m123",
            "frame_start": "7",
            "frame_end": "20",
        })

    run_tracing.assert_called_once_with(movie_id="m123", frame_start=7, frame_end=20)


def test_process_tracing_message_passes_job_id_to_runner():
    with patch("resize_app.lambda_tracing_handler.movie_glue.run_tracing") as run_tracing:
        lambda_tracing_handler.process_tracing_message({"movie_id": "m123", "job_id": "j1"})

    run_tracing.assert_called_once_with(movie_id="m123", frame_start=0, frame_end=None, job_id="j1")


def test_process_tracing_message_rejects_missing_movie_id():
    with pytest.raises(ValueError, match="movie_id is required"):
        lambda_tracing_handler.process_tracing_message({"frame_start": 7})


def async_event(*, stack_name="test-stack", job=None):
    """Return one representative custom EventBridge event."""
    detail = async_work.AsyncWorkDetail(
        stack_name=stack_name,
        job=job or async_work.TraceJob(movie_id="m123", frame_start=7),
    )
    return {
        "id": "event-1",
        "source": async_work.EVENT_SOURCE,
        "detail-type": async_work.EVENT_DETAIL_TYPE,
        "detail": detail.model_dump(mode="json"),
    }


def test_process_async_work_event_validates_stack_and_dispatches(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "test-stack")
    job = async_work.TraceJob(movie_id="m123", frame_start=7, frame_end=20)

    with patch("resize_app.lambda_tracing_handler.process_job") as process_job:
        response = lambda_tracing_handler.process_async_work_event(
            async_event(job=job)
        )

    process_job.assert_called_once_with(job)
    assert response == {"processed": True, "job_type": "trace", "movie_id": "m123"}


def test_process_async_work_event_rejects_another_stack(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "test-stack")

    with pytest.raises(ValueError, match="does not belong"):
        lambda_tracing_handler.process_async_work_event(
            async_event(stack_name="other-stack")
        )
