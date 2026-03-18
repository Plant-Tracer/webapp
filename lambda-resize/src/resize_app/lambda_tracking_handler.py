"""
Lambda entry points for tracking: direct invoke (no Flask) and SQS.
"""

import json
import os

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response,
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord

from .src.app.constants import C
from .src.app.odb import InvalidMovie_Id, get_movie_metadata
from . import tracker

LOGGER = Logger(service="planttracer")
MAX_BATCH_SIZE = 500
CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

processor = BatchProcessor(event_type=EventType.SQS)


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


def handler(event, context=None):
    """
    Lambda handler for running tracking via direct invoke or API Gateway.
    Event: {"user_id": str, "movie_id": str, "frame_start": int (optional, default 0)}
    or API Gateway: {"body": "{\"user_id\":\"...\",\"movie_id\":\"...\",\"frame_start\":0}"}
    """
    del context  # unused in this handler
    try:
        user_id, movie_id, frame_start = _parse_event(event)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        LOGGER.exception("Bad event: %s", exc)
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(exc)}),
        }
    tracker.run_tracking(user_id=user_id, movie_id=movie_id, frame_start=frame_start)
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({C.API_KEY_ERROR: False, C.API_KEY_MESSAGE: "Tracking completed"}),
    }


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def record_handler(record: SQSRecord):
    """
    Process a single SQS message.
    If this raises an exception, BatchProcessor marks only this record for retry.
    """
    body_str = record.body or "{}"
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError as exc:
        LOGGER.error("Invalid JSON in SQS body: %s", exc)
        raise

    user_id = body.get("user_id")
    movie_id = body.get("movie_id")
    frame_start = _safe_int(body.get("frame_start", 0))
    origin_start = _safe_int(body.get("origin_start", frame_start))
    batch_size = _safe_int(body.get("batch_size", MAX_BATCH_SIZE)) or MAX_BATCH_SIZE
    batch_size = max(1, min(batch_size, MAX_BATCH_SIZE))

    if not user_id or not movie_id:
        raise ValueError("user_id and movie_id are required in SQS message")

    LOGGER.info(
        "SQS tracking request: movie_id=%s user_id=%s frame_start=%s origin_start=%s batch_size=%s",
        movie_id,
        user_id,
        frame_start,
        origin_start,
        batch_size,
    )

    max_frame = frame_start + batch_size - 1
    tracker.run_tracking(
        user_id=user_id,
        movie_id=movie_id,
        frame_start=frame_start,
        max_frame=max_frame,
    )
    LOGGER.info(
        "Completed tracking batch: movie_id=%s user_id=%s frame_start=%s max_frame=%s",
        movie_id,
        user_id,
        frame_start,
        max_frame,
    )

    # Decide whether to enqueue a follow-up batch.
    try:
        movie = get_movie_metadata(movie_id=movie_id)
    except InvalidMovie_Id as exc:
        LOGGER.exception("get_movie_metadata failed for %s: %s", movie_id, exc)
        # Raise so this message can be retried if metadata is temporarily unavailable.
        raise

    last = movie.get("last_frame_tracked")
    total_frames = movie.get("total_frames")
    if last is None:
        return
    try:
        last = int(last)
    except (TypeError, ValueError):
        return

    # Hard safety cap at frame 9999 and (if known) last real frame.
    max_allowed = 9999
    if total_frames:
        try:
            max_allowed = min(max_allowed, int(total_frames) - 1)
        except (TypeError, ValueError):
            max_allowed = 9999

    # Monotonicity guard: only move forward.
    if last < frame_start or last >= max_allowed:
        return

    next_start = last + 1
    if next_start > max_allowed:
        return

    # Explicitly abort (for this chain) if we are not moving strictly
    # forward relative to both the original and current batch start.
    if next_start <= origin_start or next_start <= frame_start:
        LOGGER.error(
            "Refusing to enqueue non-advancing batch: movie_id=%s "
            "origin_start=%s frame_start=%s last=%s next_start=%s",
            movie_id,
            origin_start,
            frame_start,
            last,
            next_start,
        )
        return

    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    if not queue_url:
        LOGGER.error("TRACKING_QUEUE_URL not configured for follow-up batch")
        return

    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))
    msg = {
        "user_id": user_id,
        "movie_id": movie_id,
        "frame_start": next_start,
        "origin_start": origin_start,
        "batch_size": 100,
    }
    LOGGER.info("Enqueuing follow-up SQS batch: %s", msg)
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))


def sqs_handler(event, context=None):
    """
    SQS event source for tracking jobs.
    Each record body is JSON: {"user_id": "...", "movie_id": "...", "frame_start": int, "batch_size": int}.
    Returns partial item failures so that only bad messages are retried.
    """
    LOGGER.info("sqs_handler invoked with %d record(s)", len(event.get("Records", [])))
    return process_partial_response(
        event=event,
        record_handler=record_handler,
        processor=processor,
        context=context,
    )
