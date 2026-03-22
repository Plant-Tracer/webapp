"""
Lambda entry point for tracking only. No Flask.
Invoke with payload: {"user_id": "...", "movie_id": "...", "frame_start": 0}.
"""

import json
import logging
import os

import boto3

from .src.app.constants import C
from .lambda_tracking_env import LambdaTrackingEnv
from . import tracker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

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


def handler(event, context=None):
    """
    Lambda handler for running tracking.
    Event: {"user_id": str, "movie_id": str, "frame_start": int (optional, default 0)}
    or API Gateway: {"body": "{\"user_id\":\"...\",\"movie_id\":\"...\",\"frame_start\":0}"}
    """
    del context  # unused in this handler
    try:
        user_id, movie_id, frame_start = _parse_event(event)
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        logger.exception("Bad event: %s", e)
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(e)}),
        }
    try:
        env = LambdaTrackingEnv()
        tracker.run_tracking(user_id=user_id, movie_id=movie_id, frame_start=frame_start, env=env)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({C.API_KEY_ERROR: False, C.API_KEY_MESSAGE: "Tracking completed"}),
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Tracking failed: %s", e)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(e)}),
        }


def sqs_handler(event, context=None):
    """
    SQS event source for tracking jobs.
    Each record body is JSON: {"user_id": "...", "movie_id": "...", "frame_start": int, "batch_size": int}.
    """
    del context  # unused in this handler
    env = LambdaTrackingEnv()
    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))

    for record in event.get("Records", []):
        try:
            body = json.loads(record.get("body") or "{}")
            user_id = body["user_id"]
            movie_id = body["movie_id"]
            frame_start = int(body.get("frame_start", 0))
            origin_start = int(body.get("origin_start", frame_start))
            batch_size = int(body.get("batch_size", 500)) or 500
            batch_size = max(1, min(batch_size, 500))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Bad SQS record: %s", exc)
            continue

        try:
            max_frame = frame_start + batch_size - 1
            tracker.run_tracking(
                user_id=user_id,
                movie_id=movie_id,
                frame_start=frame_start,
                env=env,
                max_frame=max_frame,
            )

            # Decide whether to enqueue a follow-up batch.
            try:
                movie = env.get_movie_metadata(movie_id)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.exception("get_movie_metadata failed for %s: %s", movie_id, exc)
                continue

            last = movie.get("last_frame_tracked")
            total_frames = movie.get("total_frames")
            if last is None:
                continue
            try:
                last = int(last)
            except (TypeError, ValueError):
                continue

            # Hard safety cap at frame 9999 and (if known) last real frame.
            max_allowed = 9999
            if total_frames:
                try:
                    max_allowed = min(max_allowed, int(total_frames) - 1)
                except (TypeError, ValueError):
                    max_allowed = 9999

            # Monotonicity guard: only move forward.
            if last < frame_start or last >= max_allowed:
                continue

            next_start = last + 1
            if next_start > max_allowed:
                continue

            # Explicitly abort (for this chain) if we are not moving strictly
            # forward relative to both the original and current batch start.
            if next_start <= origin_start or next_start <= frame_start:
                logger.error(
                    "Refusing to enqueue non-advancing batch: movie_id=%s "
                    "origin_start=%s frame_start=%s last=%s next_start=%s",
                    movie_id,
                    origin_start,
                    frame_start,
                    last,
                    next_start,
                )
                continue

            if queue_url:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(
                        {
                            "user_id": user_id,
                            "movie_id": movie_id,
                            "frame_start": next_start,
                            "origin_start": origin_start,
                            "batch_size": 100,
                        }
                    ),
                )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Tracking failed for movie_id=%s: %s", movie_id, exc)

    return {}
