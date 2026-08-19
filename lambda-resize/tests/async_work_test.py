"""Tests for the custom EventBridge asynchronous-work contract."""

import json
from types import SimpleNamespace

import pytest

from resize_app import async_work
from resize_app import main
from resize_app.src.app.constants import C


def recording_events_client(response):
    """Return a minimal client that records its PutEvents entries."""
    client = SimpleNamespace(entries=None)

    def put_events(*, Entries):  # pylint: disable=invalid-name
        client.entries = Entries
        return response

    client.put_events = put_events
    return client


def test_publish_job_emits_stack_scoped_pydantic_event(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "test-stack")
    client = recording_events_client({
        "FailedEntryCount": 0,
        "Entries": [{"EventId": "event-1"}],
    })
    monkeypatch.setattr(async_work, "eventbridge_client", lambda: client)

    async_work.publish_job(async_work.TraceJob(
        movie_id="m123",
        frame_start=7,
        frame_end=20,
        job_id="job-123",
    ))

    assert client.entries is not None
    assert len(client.entries) == 1
    entry = client.entries[0]
    assert entry["EventBusName"] == "default"
    assert entry["Source"] == async_work.EVENT_SOURCE
    assert entry["DetailType"] == async_work.EVENT_DETAIL_TYPE
    assert json.loads(entry["Detail"]) == {
        "stack_name": "test-stack",
        "job": {
            "job_type": "trace",
            "movie_id": "m123",
            "frame_start": 7,
            "frame_end": 20,
            "job_id": "job-123",
        },
    }


def test_publish_job_rejects_partial_eventbridge_failure(monkeypatch):
    monkeypatch.setenv(C.PLANTTRACER_STACK_NAME, "test-stack")
    client = recording_events_client({
        "FailedEntryCount": 1,
        "Entries": [{"ErrorCode": "InternalFailure", "ErrorMessage": "try again"}],
    })
    monkeypatch.setattr(async_work, "eventbridge_client", lambda: client)

    with pytest.raises(RuntimeError, match="InternalFailure: try again"):
        async_work.publish_job(async_work.PostUploadJob(movie_id="m123"))


def test_lambda_handler_dispatches_custom_event(monkeypatch):
    event = {
        "id": "event-1",
        "source": async_work.EVENT_SOURCE,
        "detail-type": async_work.EVENT_DETAIL_TYPE,
        "detail": {
            "stack_name": "test-stack",
            "job": {"job_type": "post_upload", "movie_id": "m123"},
        },
    }
    monkeypatch.setattr(
        main.lambda_tracing_handler,
        "process_async_work_event",
        lambda received: {"received": received["id"]},
    )

    context = SimpleNamespace(
        function_name="test-async-work",
        memory_limit_in_mb=128,
        invoked_function_arn="arn:aws:lambda:us-east-1:123:function:test-async-work",
        aws_request_id="test-request-id",
    )
    assert main.lambda_handler(event, context) == {"received": "event-1"}
