"""
Local HTTP bridge for lambda-resize.

Runs the Lambda HTTP API in a separate local process so the browser can talk to
it over HTTP while Flask continues serving HTML and metadata.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
from typing import Any

from flask import Flask, Response, request

from resize_app import lambda_tracking_handler
from resize_app import local_queue
from resize_app import main as resize_main

from app.constants import configure_local_environment as configure_shared_local_environment
from app.constants import logger

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9811

bridge_app = Flask(__name__)


class DummyContext:
    function_name = "local-lambda-debug"
    memory_limit_in_mb = 1024
    invoked_function_arn = "arn:aws:lambda:local:000000000000:function:local-lambda-debug"
    aws_request_id = "local-lambda-request"


def build_api_gateway_v2_event() -> dict[str, Any]:
    body_bytes = request.get_data(cache=True)
    try:
        body = body_bytes.decode("utf-8")
        is_base64 = False
    except UnicodeDecodeError:
        body = base64.b64encode(body_bytes).decode("ascii")
        is_base64 = True

    headers = dict(request.headers.items())
    query_string = request.query_string.decode("utf-8")
    query_params = request.args.to_dict(flat=True)
    event = {
        "version": "2.0",
        "routeKey": f"{request.method} {request.path}",
        "rawPath": request.path,
        "rawQueryString": query_string,
        "headers": headers,
        "queryStringParameters": query_params if query_params else None,
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": request.method,
                "path": request.path,
                "sourceIp": request.remote_addr or "127.0.0.1",
            },
        },
        "body": body if body_bytes else "",
        "isBase64Encoded": is_base64,
    }
    return event


def lambda_result_to_response(result: dict[str, Any]) -> Response:
    status_code = int(result.get("statusCode", 200))
    headers = dict(result.get("headers") or {})
    body = result.get("body", "")
    if result.get("isBase64Encoded"):
        payload = base64.b64decode(body or b"")
    elif isinstance(body, (dict, list)):
        payload = json.dumps(body)
        headers.setdefault("Content-Type", "application/json")
    else:
        payload = body
    return Response(response=payload, status=status_code, headers=headers)


@bridge_app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@bridge_app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def handle_lambda_bridge(path: str):
    del path
    event = build_api_gateway_v2_event()
    logger.info("local lambda bridge method=%s path=%s", request.method, request.path)
    result = resize_main.lambda_handler(event, DummyContext())
    return lambda_result_to_response(result)


def main():
    parser = argparse.ArgumentParser(description="Run lambda-resize locally over HTTP")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    configure_shared_local_environment(include_tracking_queue=True)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not bridge_app.debug:
        local_queue.start_worker(processor=lambda_tracking_handler.process_tracking_message)
        atexit.register(local_queue.stop_worker)

    logger.info("Starting local lambda debug server at http://%s:%s", args.host, args.port)
    bridge_app.run(host=args.host, port=args.port, debug=True, use_reloader=True, threaded=True)


if __name__ == "__main__":
    main()
