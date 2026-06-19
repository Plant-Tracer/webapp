"""
Lambda entry points for tracing: direct invoke (no Flask) and SQS.
"""

import json
import time

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

from . import movie_glue

LOGGER = Logger(service="planttracer")
MAX_BATCH_SIZE = 500
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def process_tracing_message(body: dict):
    movie_id = body.get("movie_id")
    frame_start = _safe_int(body.get("frame_start", 0))
    frame_end = body.get("frame_end")
    if frame_end is not None:
        frame_end = _safe_int(frame_end, None)

    if not movie_id:
        raise ValueError("movie_id is required in SQS message")

    t0 = time.time()
    LOGGER.info("SQS Start tracing batch: movie_id=%s frame_start=%s frame_end=%s", movie_id, frame_start, frame_end)
    movie_glue.run_tracing(movie_id=movie_id, frame_start=frame_start, frame_end=frame_end)
    LOGGER.info(
        "SQS Completed tracing batch: movie_id=%s frame_start=%s frame_end=%s elapsed_time=%s",
        movie_id,
        frame_start,
        frame_end,
        time.time() - t0,
    )

def process_tracing_record(record: SQSRecord):
    """
    Process a single SQS message.
    If this raises an exception, BatchProcessor marks only this record for retry.
    """
    try:
        body = json.loads(record.body or "{}")
    except json.JSONDecodeError as exc:
        LOGGER.error("Invalid JSON in SQS body: %s", exc)
        raise
    process_tracing_message(body)
