"""
Lambda entry point for tracking only. No Flask.
Invoke with payload: {"user_id": "...", "movie_id": "...", "frame_start": 0}.
"""

import json
import logging

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
    # pylint: disable=unused-argument
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
    # pylint: disable=unused-argument
    env = LambdaTrackingEnv()
    for record in event.get("Records", []):
        try:
            body = json.loads(record.get("body") or "{}")
            user_id = body["user_id"]
            movie_id = body["movie_id"]
            frame_start = int(body.get("frame_start", 0))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Bad SQS record: %s", exc)
            continue
        try:
            tracker.run_tracking(user_id=user_id, movie_id=movie_id, frame_start=frame_start, env=env)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Tracking failed for movie_id=%s: %s", movie_id, exc)
    return {}
