"""
Lambda HTTP API entry point. Parses the event and delegates to resize API handlers.
"""

import time
from typing import Any, Dict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig, Response
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

from .src.app import odb
from .src.app.odb import (
    DDBO,
    USER_ID,
    MOVIE_ID,
    PROCESSING_STATE,
    PROCESSING_STATE_TRACKING,
    TRACKING_STATUS_UPDATED_AT,
)
from .resize import (
    api_get_frame,
    api_heartbeat,
    api_log,
    api_ping,
    api_resize,
    api_rotate_and_zip,
    api_start_processing,
    api_status,
)
from .lambda_tracking_handler import sqs_handler

LOGGER = Logger(service="planttracer")

# Permissive CORS automatically applied to all routes
cors_config = CORSConfig(
    allow_origin="*",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app = APIGatewayHttpResolver(cors=cors_config)


def json_error(status_code: int, message: str) -> Response:
    """Helper to return JSON errors using native Powertools Response."""
    import json
    return Response(
        status_code=status_code,
        content_type="application/json",
        body=json.dumps({"error": True, "message": message})
    )


# Note: We replaced `resp_json` dependency with `json_error`
def api_track_movie(payload: Dict[str, Any]) -> Any:
    # Example integration for your legacy api_track_movie
    movie_id = payload.get("movie_id")
    if not movie_id:
        return json_error(400, "Missing movie_id")
    return {"error": False, "message": "Tracking started"}


def api_new_frame(payload: Dict[str, Any]) -> Any:
    # Example integration for your legacy api_new_frame
    return {"error": False, "message": "Frame processed"}


@app.post("/api/v1")
def handle_post_actions():
    """
    Main RPC dispatcher based on JSON body 'action' field.
    """
    event = app.current_event.raw_event
    context = app.current_event.lambda_context
    payload = app.current_event.json_body or {}

    action = (payload.get("action") or "").lower()

    if action == "ping":
        return api_ping(event, context)
    if action == "resize-start":
        return api_resize(event, context, payload)
    if action == "start-processing":
        return api_start_processing(payload)
    if action == "rotate-and-zip":
        return api_rotate_and_zip(payload)
    if action == "track-movie":
        return api_track_movie(payload)
    if action == "new-frame":
        return api_new_frame(payload)
    if action == "heartbeat":
        return api_heartbeat(event, context)
    if action == "log":
        return api_log()

    return json_error(400, f"Unknown action {action}")


@app.get("/api/v1/frame")
def handle_get_frame() -> Any:
    """GET /api/v1/frame delegate."""
    return api_get_frame(app.current_event.raw_event)


@app.get("/api/v1/status")
def handle_get_status() -> Any:
    return api_status()


@LOGGER.inject_lambda_context(log_event=True)
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Unified Lambda entrypoint: dispatch between HTTP API and SQS events."""
    if isinstance(event, dict) and "Records" in event:
        # Route to SQS handler for partial batch processing
        return sqs_handler(event, context)
    
    # Powertools resolves HTTP events natively
    return app.resolve(event, context)
