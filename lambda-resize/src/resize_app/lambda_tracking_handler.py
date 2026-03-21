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

def _parse_event(event):
    """Extract user_id, movie_id, frame_start from API Gateway or direct invoke payload."""
    if isinstance(event.get("body"), str):
        body = json.loads(event["body"])
    else:
        body = event
    user_id = body.get("user_id")
    movie_id = body.get("movie_id")
    frame_start = body.get("frame_start", 0)
    if not user_id or not movie_id:
        raise ValueError("user_id and movie_id required")
    return user_id, movie_id, int(frame_start)


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

    user_id = body.get("user_id")
    movie_id = body.get("movie_id")
    frame_start = _safe_int(body.get("frame_start", 0))

    if not user_id or not movie_id:
        raise ValueError("user_id and movie_id are required in SQS message")

    t0 = time.time()
    LOGGER.info( "SQS Start tracking batch: movie_id=%s user_id=%s frame_start=%s ",
                 movie_id, user_id, frame_start)
    movie_glue.run_tracing( user_id=user_id, movie_id=movie_id, frame_start=frame_start)
    LOGGER.info( "SQS Completed tracking batch: movie_id=%s user_id=%s frame_start=%s elapsed_time=%s",
                 movie_id, user_id, frame_start, time.time()-t0)
