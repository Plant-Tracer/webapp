"""
Minimal Lambda entry point for tracking only. No Flask.
Invoke with payload: {"user_id": "...", "movie_id": "...", "frame_start": 0}.
"""

import json
import logging

from .constants import C
from .lambda_tracking_env import LambdaTrackingEnv
from . import tracker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


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
    Lambda handler for running tracking. No Flask/odb loaded.
    Event: {"user_id": str, "movie_id": str, "frame_start": int (optional, default 0)}
    or API Gateway: {"body": "{\"user_id\":\"...\",\"movie_id\":\"...\",\"frame_start\":0}"}
    """
    # pylint: disable=unused-argument
    try:
        user_id, movie_id, frame_start = _parse_event(event)
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        logger.exception("Bad event: %s", e)
        return {"statusCode": 400, "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(e)})}
    try:
        env = LambdaTrackingEnv()
        tracker.run_tracking(user_id=user_id, movie_id=movie_id, frame_start=frame_start, env=env)
        return {"statusCode": 200, "body": json.dumps({C.API_KEY_ERROR: False, C.API_KEY_MESSAGE: "Tracking completed"})}
    except tracker.MetadataNotReadyError as e:
        logger.warning("Metadata not ready: %s", e)
        return {"statusCode": 503, "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(e)})}
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Tracking failed: %s", e)
        return {"statusCode": 500, "body": json.dumps({C.API_KEY_ERROR: True, C.API_KEY_MESSAGE: str(e)})}
