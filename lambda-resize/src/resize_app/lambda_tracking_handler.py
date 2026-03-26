"""
Lambda entry points for tracking: direct invoke (no Flask) and SQS.
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

def process_tracking_record(record: SQSRecord):
    """
    Process a single SQS message.
    If this raises an exception, BatchProcessor marks only this record for retry.
    """
    try:
        body = json.loads(record.body or "{}")
    except json.JSONDecodeError as exc:
        LOGGER.error("Invalid JSON in SQS body: %s", exc)
        raise

    movie_id = body.get("movie_id")
    frame_start = _safe_int(body.get("frame_start", 0))

    if not movie_id:
        raise ValueError("movie_id is required in SQS message")

    t0 = time.time()
    LOGGER.info( "SQS Start tracking batch: movie_id=%s frame_start=%s ",
                 movie_id, frame_start)
    movie_glue.run_tracing( movie_id=movie_id, frame_start=frame_start)
    LOGGER.info( "SQS Completed tracking batch: movie_id=%s frame_start=%s elapsed_time=%s",
                 movie_id, frame_start, time.time()-t0)
