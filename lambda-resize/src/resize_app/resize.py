"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
import base64
import binascii
import json
import os
import sys
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Tuple, Optional

from .common import LOGGER
from .src.app import odb
from .src.app.odb import DDBO

__version__ = "0.1.0"

# Optional status message key in logs table; api_status() may display it if set
LOG_ID_STATUS_PING = "lambda-status-ping"

################################################################
## Minimal support for a Python-based website in Lamda with jinja2 support
##

# jinja2

def _json_serial(obj: Any) -> Any:
    """Default for json.dumps: DynamoDB returns numbers as Decimal."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def resp_json( status: int, body: Dict[str, Any], headers: Optional[Dict[str, str]] = None ) -> Dict[str, Any]:
    """End HTTP event processing with a JSON object"""
    LOGGER.debug("resp_json(status=%s) body=%s", status, body)
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            **(headers or {}),
        },
        "body": json.dumps(body, default=_json_serial),
    }


def _with_request_log_level(payload: Dict[str, Any]):
    """Context manager to temporarily adjust log level from JSON (log_level or LOG_LEVEL)."""
    class _Ctx:
        def __init__(self):
            self.old = LOGGER.level

        def __enter__(self):
            lvl = payload.get("log_level") or payload.get("LOG_LEVEL")
            if isinstance(lvl, str):
                LOGGER.setLevel(lvl)
            return self

        def __exit__(self, exc_type, exc, tb):
            LOGGER.setLevel(self.old)

    return _Ctx()


################################################################
## api code.
## api calls do not use sessions. Authenticated APIs (e.g. api_register, api_grade)
## authenticate with api_authenticate(payload), which returns the user directory.

def api_heartbeat(event, context)  -> Dict[str, Any]:
    """Called periodically. Not authenticated. Main purpose clean up active camera sessions"""
    LOGGER.info("heartbeat event=%s context=%s", event, context)
    return resp_json( 200, { "now": time.time() } )


def api_resize(event, context, payload)  -> Dict[str, Any]:
    """
    1. Validate api_key.
    2. Create the movie if it is not provided.
    3. Generate N S3 uploads, starting with image N.

    :param payload['api_key']: - api_key
    :param payload['movie_id']: - movie_id if upload already in process
    :param payload['start']: - first frame
    :param payload['count']: - number of frames
    :return: dict['signed_urls'] = array of requested URLs
             dict['start'] = first URL frame number
    """

    LOGGER.info("api_resize event=%s context=%s payload=%s", event, context, payload)
    start = time.time()
    end = time.time()
    return resp_json(200, {'start':start, 'end':end})

################################################################
## Parse Lambda Events and cookies
def parse_event(event: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """parse HTTP API v2 event.
    :param event: AWS Lambda HTTP API v2 event to parse
    :return (method,path,payload) - method - HTTP Method; path=HTTP Path; payload=JSON body if POST
    """
    stage = event.get("requestContext", {}).get("stage", "")
    path = event.get("rawPath") or event.get("path") or "/"
    if stage and path.startswith("/" + stage):
        path = path[len(stage) + 1 :] or "/"
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
    )
    body = event.get("body")
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body or "").decode("utf-8", "replace")
        except binascii.Error:
            body = None
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}
    return method, path, payload


def write_log(message, *, time_t=None, course_id=None, log_user_id=None, ipaddr=None):
    """Write a log entry to the DynamoDB logs table (same table as main app)."""
    if time_t is None:
        time_t = time.time()

    ddbo = DDBO()
    item = {
        "log_id": str(uuid.uuid4()),
        "time_t": int(time_t),
        "message": message,
    }
    if course_id is not None:
        item["course_id"] = course_id
    if log_user_id is not None:
        item["user_id"] = log_user_id
    if ipaddr is not None:
        item["ipaddr"] = ipaddr
    ddbo.logs.put_item(Item=item)


def _get_recent_logs(limit: int = 5) -> Dict[str, Any]:
    """
    Fetch recent log entries from the DynamoDB logs table, sorted by time_t descending.
    This scans the table and sorts client-side; acceptable for small log volumes and status checks.
    """
    ddbo = DDBO()
    items: list[Dict[str, Any]] = []
    last_evaluated_key = None
    scan_kwargs: Dict[str, Any] = {
        "ProjectionExpression": "log_id, time_t, message, course_id, user_id, ipaddr",
    }

    while True:
        if last_evaluated_key:
            scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
        elif "ExclusiveStartKey" in scan_kwargs:
            del scan_kwargs["ExclusiveStartKey"]
        response = ddbo.logs.scan(**scan_kwargs)
        items.extend(response.get("Items") or [])
        last_evaluated_key = response.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    items.sort(key=lambda x: x.get("time_t", 0), reverse=True)
    return {
        "items": items[:limit],
    }

def api_ping(event, context):
    write_log('ping')
    return resp_json( 200,
                      { "error": False, "message": "ok", "path": sys.path,
                        "event" : dict(event),
                        "context": dict(context),
                        "environ": dict(os.environ) } )

def api_log():
    logs = odb.get_logs(user_id=None)
    return resp_json( 400, {"logs":logs})


def api_status() -> Dict[str, Any]:
    """Return overall status plus recent DynamoDB log entries (for bootstrap and S3 watcher debug)."""
    try:
        now = time.time()
        status_version = time.strftime("%H%M%S", time.gmtime(now))

        # Record this status check in both CloudWatch Logs and DynamoDB logs.
        LOGGER.info("status check version=%s", status_version)
        write_log(f"lambda-status version={status_version}", time_t=now)

        ddbo = DDBO()
        r = ddbo.logs.get_item(Key={"log_id": LOG_ID_STATUS_PING})
        item = r.get("Item")
        status_message = (item.get("message") or "") if item else None
        recent = _get_recent_logs(limit=5)
        return resp_json(
            200,
            {
                "status": "ok",
                "status_message": status_message,
                "status_version": status_version,
                "recent_logs": recent.get("items", []),
            },
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.exception("api_status failed: %s", e)
        return resp_json(500, {"status": "error", "message": str(e)})

################################################################
## main entry point from lambda system

# pylint: disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """Called by Lambda for HTTP API requests (no S3 event invocation)."""
    method, path, payload = parse_event(event)

    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # Status (GET; health check)
                case ("GET", "/status", _):
                    return api_status()
                case ("GET", "/prod/status", _):
                    return api_status()

                ################################################################
                # JSON API Actions
                case (_, "/api/v1", "ping"):
                    return api_ping(event,context)

                case (_, '/api/v1/ping', _):
                    return api_ping(event,context)

                case ("POST", "/api/v1", "resize-start"):
                    return api_resize(event, context, payload)

                case (_, "/api/v1", "heartbeat"):
                    return api_heartbeat(event, context)

                case (_, "/api/v1", "log"):
                    return api_log()

                case (_, "/api/v1", _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

                ################################################################
                # error
                case (_, _, _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("Unhandled exception! e=%s", e)

            # Return JSON for API requests
            return resp_json(500, {"error": True, "message": str(e)})
