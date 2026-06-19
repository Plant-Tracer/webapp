import threading

import pytest

from resize_app.local_queue import LocalTracingQueue


def test_local_tracing_queue_requires_processor_before_start():
    tracing_queue = LocalTracingQueue()

    with pytest.raises(RuntimeError, match="without a processor"):
        tracing_queue.start_worker()


def test_local_tracing_queue_processes_enqueued_message():
    tracing_queue = LocalTracingQueue()
    processed = []
    processed_event = threading.Event()

    def processor(message):
        processed.append(message)
        processed_event.set()

    tracing_queue.start_worker(processor=processor)
    try:
        tracing_queue.enqueue_message({"movie_id": "m123", "frame_start": 7, "frame_end": 20})
        assert processed_event.wait(timeout=2)
    finally:
        tracing_queue.stop_worker()

    assert processed == [{"movie_id": "m123", "frame_start": 7, "frame_end": 20}]
