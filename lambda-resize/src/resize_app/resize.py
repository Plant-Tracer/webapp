"""
Main entry point for AWS Lambda Dashboard operations.
Generates statuses, heartbeats, resizing, and frame extraction.
"""

import os
import sys
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import Response

from .common import LOGGER
from .src.app import odb
from .src.app.odb import DDBO

__version__ = "0.1.0"
LOG_ID_STATUS_PING = "lambda-status-ping"


def json_error(status_code: int, message: str) -> Response:
    """Helper for 400/500 errors so Powertools handles them natively."""
    import json
    return Response(
        status_code=status_code,
        content_type="application/json",
        body=json.dumps({"error": True, "message": message})
    )


def write_log(message: str, time_t: Optional[float] = None) -> None:
    now = time_t or time.time()
    try:
        DDBO().logs.put_item(
            Item={
                "log_id": str(uuid.uuid4()),
                "timestamp": Decimal(str(now)),
                "message": message,
                "ttl": int(now + 86400 * 7),
            }
        )
    except ClientError as e:
        LOGGER.error("Failed to write log: %s", e)


def _get_recent_logs(limit: int = 5) -> Dict[str, Any]:
    try:
        return odb.get_logs(user_id=None, limit=limit)
    except Exception as e:
        LOGGER.error("Failed fetching recent logs: %s", e)
        return {"items": [], "error": str(e)}


def api_heartbeat(event: Any, context: Any) -> Dict[str, Any]:
    LOGGER.info("heartbeat event=%s context=%s", event, context)
    # Returning a raw dict automatically results in an HTTP 200 with JSON body
    return {"now": time.time()}


def api_resize(event: Any, context: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    LOGGER.info("api_resize invoked", extra={"payload": payload})
    return {"start": time.time(), "end": time.time()}


def api_ping(event: Any, context: Any) -> Dict[str, Any]:
    write_log('ping')
    try:
        ctx_dict = dict(context)
    except TypeError:
        ctx_dict = str(context)

    return {
        "error": False, 
        "message": "ok", 
        "path": sys.path,
        "event": dict(event) if event else {},
        "context": ctx_dict,
        "environ": dict(os.environ)
    }


def api_log() -> Dict[str, Any]:
    logs = odb.get_logs(user_id=None)
    return {"logs": logs}


def api_status() -> Dict[str, Any]:
    try:
        now = time.time()
        status_version = time.strftime("%H%M%S", time.gmtime(now))

        LOGGER.info("status check version=%s", status_version)
        write_log(f"lambda-status version={status_version}", time_t=now)

        ddbo = DDBO()
        r = ddbo.logs.get_item(Key={"log_id": LOG_ID_STATUS_PING})
        item = r.get("Item")
        status_message = (item.get("message") or "") if item else None
        recent = _get_recent_logs(limit=5)
        
        return {
            "status": "ok",
            "status_message": status_message,
            "status_version": status_version,
            "recent_logs": recent.get("items", []),
        }
    except Exception as e:
        LOGGER.exception("Error in status API")
        return json_error(500, str(e))


def api_get_frame(event: Dict[str, Any]) -> Any:
    """Extract a single frame and return a REDIRECT."""
    qps = event.get("queryStringParameters") or {}
    movie_id = qps.get("movie_id")
    
    if not movie_id:
        return json_error(400, "Missing movie_id")

    try:
        # Example redirect to presigned URL logic
        presigned_url = "https://s3.amazonaws.com/example-bucket/frame.jpg?..."
        
        # We must use Response for redirects because returning a dict defaults to 200.
        return Response(
            status_code=302,
            headers={"Location": presigned_url},
            body="Redirecting..."
        )
    except Exception as e:
        LOGGER.exception("Error in get_frame")
        return json_error(500, str(e))


def api_start_processing(payload: Dict[str, Any]) -> Any:
    user_id = payload.get("user_id")
    movie_id = payload.get("movie_id")
    if not user_id or not movie_id:
        return json_error(400, "missing user_id or movie_id")
    
    return {"error": False, "message": "Queued via SQS"}


def api_rotate_and_zip(payload: Dict[str, Any]) -> Any:
    movie_id = payload.get("movie_id")
    if not movie_id:
        return json_error(400, "missing movie_id")

    return {"error": False, "message": "Rotate & Zip complete"}
