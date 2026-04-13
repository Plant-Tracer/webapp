"""
Local async queue used by the local Lambda debug server.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

from aws_lambda_powertools import Logger

LOGGER = Logger(service="planttracer")
TrackingProcessor = Callable[[dict[str, Any]], None]


class LocalTrackingQueue:
    """Singleton queue manager for local retracing work."""

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._worker_thread: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._processor: TrackingProcessor | None = None

    def _worker_main(self) -> None:
        LOGGER.info("Local tracking queue worker started")
        while not self._stop_event.is_set():
            message = self._queue.get()
            try:
                if message is None:
                    continue
                if self._processor is None:
                    raise RuntimeError("Local tracking queue processor is not configured")
                self._processor(message)
            finally:
                self._queue.task_done()
        LOGGER.info("Local tracking queue worker stopped")

    def start_worker(self, *, processor: TrackingProcessor | None = None) -> None:
        with self._worker_lock:
            if processor is not None:
                self._processor = processor
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            if self._processor is None:
                raise RuntimeError("Cannot start local tracking queue without a processor")
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._worker_main, name="local-tracking-queue", daemon=True)
            self._worker_thread.start()

    def enqueue_message(self, message: dict[str, Any]) -> None:
        self.start_worker()
        self._queue.put(message)

    def stop_worker(self, timeout: float = 2.0) -> None:
        with self._worker_lock:
            if self._worker_thread is None:
                return
            self._stop_event.set()
            self._queue.put(None)
            self._worker_thread.join(timeout=timeout)
            self._worker_thread = None


LOCAL_TRACKING_QUEUE = LocalTrackingQueue()


def start_worker(*, processor: TrackingProcessor | None = None) -> None:
    LOCAL_TRACKING_QUEUE.start_worker(processor=processor)


def enqueue_message(message: dict[str, Any]) -> None:
    LOCAL_TRACKING_QUEUE.enqueue_message(message)


def stop_worker(timeout: float = 2.0) -> None:
    LOCAL_TRACKING_QUEUE.stop_worker(timeout=timeout)
