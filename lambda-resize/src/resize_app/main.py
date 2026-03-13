"""
Lambda HTTP API entry point. Parses the event and delegates to resize API handlers.
"""

import base64
import binascii
import json
from typing import Any, Dict, Tuple

# pylint: disable=too-many-branches, disable=unused-argument
def parse_event(event: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """Parse HTTP API v2 event.
    :param event: AWS Lambda HTTP API v2 event to parse
    :return (method, path, payload) - method - HTTP Method; path=HTTP Path; payload=JSON body if POST
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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Called by Lambda for HTTP API requests (no S3 event invocation)."""
    from .resize import (  # pylint: disable=import-outside-toplevel
        api_heartbeat,
        api_log,
        api_ping,
        api_resize,
        api_rotate_and_zip,
        api_start_processing,
        api_status,
        resp_json,
        _with_request_log_level,
    )

    method, path, payload = parse_event(event)

    with _with_request_log_level(payload):
        try:
            action = (payload.get("action") or "").lower()
            from .common import LOGGER  # pylint: disable=import-outside-toplevel

            LOGGER.info(
                "req method='%s' path='%s' action='%s' payload=%s",
                method,
                path,
                action,
                payload,
            )

            match (method, path, action):
                case ("GET", "/status", _):
                    return api_status()
                case ("GET", "/prod/status", _):
                    return api_status()

                case ("OPTIONS", "/api/v1", _):
                    return resp_json(
                        204,
                        {},
                        headers={
                            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                            "Access-Control-Allow-Headers": "*",
                        },
                    )

                case (_, "/api/v1", "ping"):
                    return api_ping(event, context)
                case (_, "/api/v1/ping", _):
                    return api_ping(event, context)

                case ("POST", "/api/v1", "resize-start"):
                    return api_resize(event, context, payload)
                case ("POST", "/api/v1", "start-processing"):
                    return api_start_processing(payload)
                case ("POST", "/api/v1", "rotate-and-zip"):
                    return api_rotate_and_zip(payload)

                case (_, "/api/v1", "heartbeat"):
                    return api_heartbeat(event, context)
                case (_, "/api/v1", "log"):
                    return api_log()

                case (_, "/api/v1", _):
                    return resp_json(400, {"error": True, "message": f"Unknown action {action}"})

                case (_, _, _):
                    return resp_json(400, {"error": True, "message": f"Unknown action {action}"})

        except Exception as e:  # pylint: disable=broad-exception-caught
            from .common import LOGGER  # pylint: disable=import-outside-toplevel

            LOGGER.exception("Unhandled exception! e=%s", e)
            return resp_json(500, {"error": True, "message": str(e)})
