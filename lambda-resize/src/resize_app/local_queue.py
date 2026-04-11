"""
Local async queue used by the local Lambda debug server.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from aws_lambda_powertools import Logger

LOGGER = Logger(service="planttracer")

_QUEUE: queue.Queue[dict[str, Any] | None] = queue.Queue()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()


def _worker_main():
    from . import lambda_tracking_handler

    LOGGER.info("Local tracking queue worker started")
    while not _STOP_EVENT.is_set():
        message = _QUEUE.get()
        try:
            if message is None:
                continue
            lambda_tracking_handler.process_tracking_message(message)
        finally:
            _QUEUE.task_done()
    LOGGER.info("Local tracking queue worker stopped")


def start_worker():
    global _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _STOP_EVENT.clear()
        _WORKER_THREAD = threading.Thread(target=_worker_main, name="local-tracking-queue", daemon=True)
        _WORKER_THREAD.start()


def enqueue_message(message: dict[str, Any]):
    start_worker()
    _QUEUE.put(message)


def stop_worker(timeout: float = 2.0):
    global _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD is None:
            return
        _STOP_EVENT.set()
        _QUEUE.put(None)
        _WORKER_THREAD.join(timeout=timeout)
        _WORKER_THREAD = None
