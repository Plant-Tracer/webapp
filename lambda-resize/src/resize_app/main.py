"""
Lambda HTTP API entry point. Parses the event and delegates to resize API handlers.
"""

import base64
import functools
import json
import os
import time
from decimal import Decimal
from typing import Any, Dict

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, CORSConfig
import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from .src.app import odb
from .src.app.odb import (
    DDBO,
    USER_ID,
    ENABLED,
    MOVIE_ID,
    PROCESSING_STATE,
    PROCESSING_STATE_TRACKING,
    MOVIE_DATA_URN,
    MOVIE_ZIPFILE_URN,
    TRACKING_STATUS_UPDATED_AT,
)
from .src.app.odb_movie_data import create_new_movie_frame
from .src.app.s3_presigned import make_signed_url, object_exists
from .resize import (
    api_get_frame,
    api_heartbeat,
    api_log,
    api_ping,
    api_resize,
    api_rotate_and_zip,
    api_start_processing,
    api_status,
    resp_json,
    resp_redirect,
)
from .lambda_tracking_handler import MAX_BATCH_SIZE

LOGGER = Logger(service="planttracer")

# Permissive CORS
cors_config = CORSConfig(
    allow_origin="*",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app = APIGatewayHttpResolver(cors=cors_config)

def movies_table():
    """Return the movies table resource used by Lambda tracking claim logic.
    DDBO() is a singleton, so no need to cache this function.
    """
    return DDBO().movies


def try_claim_tracking(movie_id):
    """Claim tracking for a movie unless a fresh run is already active."""
    now_ts = int(time.time())
    cutoff = now_ts - 3600
    item = movies_table().get_item(Key={MOVIE_ID: movie_id}, ConsistentRead=True).get("Item")
    if item:
        state = item.get(PROCESSING_STATE)
        updated_at = item.get(TRACKING_STATUS_UPDATED_AT)
        if state == PROCESSING_STATE_TRACKING and updated_at is not None:
            try:
                ts = int(updated_at)
            except (TypeError, ValueError):
                ts = 0
            if now_ts - ts < 3600:
                return False
    try:
        movies_table().update_item(
            Key={MOVIE_ID: movie_id},
            UpdateExpression="SET #ps = :tracking, #ts = :now",
            ConditionExpression=(
                Attr(PROCESSING_STATE).ne(PROCESSING_STATE_TRACKING)
                | Attr(TRACKING_STATUS_UPDATED_AT).not_exists()
                | Attr(TRACKING_STATUS_UPDATED_AT).lt(cutoff)
            ),
            ExpressionAttributeNames={"#ps": PROCESSING_STATE, "#ts": TRACKING_STATUS_UPDATED_AT},
            ExpressionAttributeValues={":tracking": PROCESSING_STATE_TRACKING, ":now": now_ts},
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True

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

def api_track_movie(payload: Dict[str, Any], resp_json: Any) -> Dict[str, Any]:
    """
    POST /api/v1 with action=track-movie. Body: api_key, movie_id, frame_start.
    Validates that api_key is valid (same as get-frame), then enqueues tracking work to SQS.
    Refuses to start if this movie is already tracking and status was updated <1 hour ago.
    This provides a rapid return and queues the tracking
    """

    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    if not queue_url:
        return resp_json(500, {"error": True, "message": "TRACKING_QUEUE_URL not configured"})
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))

    api_key = (payload.get("api_key") or "").strip()
    movie_id = (payload.get("movie_id") or "").strip()
    if not api_key or not movie_id:
        return resp_json(400, {"error": True, "message": "api_key and movie_id required"})

    try:
        frame_start = int(payload.get("frame_start", 0))
    except (TypeError, ValueError):
        frame_start = 0
    if frame_start < 0 or frame_start >= 10000:
        return resp_json(400, {"error": True, "message": "frame_start must be between 0 and 9999"})

    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None or not api_key_dict.get(ENABLED, True):
        return resp_json(401, {"error": True, "message": "invalid or disabled api_key"})

    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        return resp_json(401, {"error": True, "message": "invalid api_key"})

    if not try_claim_tracking(movie_id):
        return resp_json( 409, {
            "error": True,
            "message": "Tracking already in progress for this movie. Wait for it to finish or try again in an hour.",
        } )

    body = {
        "user_id": user_id,
        "movie_id": movie_id,
        "frame_start": frame_start,
        "origin_start": frame_start,
        "batch_size": max(1, min(int(payload.get("batch_size", 1)) or 1, MAX_BATCH_SIZE)),
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))
    return resp_json( 202, {
        "error": False,
        "accepted": True,
        "movie_id": movie_id,
        "frame_start": frame_start,
        "batch_size": body["batch_size"],
    } )


def api_get_movie_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /api/v1/movie-data?api_key=...&movie_id=...&format=zip|json (optional).
    By default returns 302 redirect to signed S3 URL for the movie.
    format=zip: 302 redirect to zip file.
    format=json: 200 JSON with url (MP4), zip_url (if present), movie_id.
    """

    params = event.get("queryStringParameters") or event.get("query_params") or {}
    api_key = (params.get("api_key") or "").strip()
    movie_id = (params.get("movie_id") or "").strip()
    fmt = (params.get("format") or "").strip().lower()
    zipfile = fmt == "zip"
    format_json = fmt == "json"
    if not api_key or not odb.is_movie_id(movie_id):
        return resp_json(400, {"error": True, "message": "api_key and movie_id required"})
    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None or not api_key_dict.get(ENABLED, True):
        return resp_json(401, {"error": True, "message": "invalid or disabled api_key"})
    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        return resp_json(401, {"error": True, "message": "invalid api_key"})
    try:
        movie = odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    except odb.UnauthorizedUser:
        return resp_json(403, {"error": True, "message": "access denied"})
    except odb.InvalidMovie_Id:
        return resp_json(404, {"error": True, "message": "movie not found"})

    data_urn = movie.get(MOVIE_ZIPFILE_URN if zipfile else MOVIE_DATA_URN)
    if not data_urn:
        return resp_json(503, {"error": True, "message": "Movie not ready (no URN)."})
    if not object_exists(data_urn):
        return resp_json(
            503,
            {"error": True, "message": "Movie still processing (upload not yet at final key). Retry in a few seconds."},
            headers={"Retry-After": "5"},
        )
    return resp_redirect(make_signed_url(urn=data_urn))


def api_new_frame(payload: Dict[str, Any], resp_json: Any) -> Dict[str, Any]:
    """
    POST /api/v1 with action=new-frame. Body: api_key, movie_id, frame_number, optional frame_base64_data.
    Creates or updates a frame record; if frame_base64_data provided, uploads image to S3.
    """

    api_key = (payload.get("api_key") or "").strip()
    movie_id = (payload.get("movie_id") or "").strip()
    try:
        frame_number = int(payload.get("frame_number", 0))
    except (TypeError, ValueError):
        return resp_json(400, {"error": True, "message": "frame_number required and must be integer"})
    frame_b64 = payload.get("frame_base64_data")
    frame_data = None
    if frame_b64:
        try:
            frame_data = base64.b64decode(frame_b64)
        except (TypeError, ValueError):
            return resp_json(400, {"error": True, "message": "invalid frame_base64_data"})
    if not api_key or not odb.is_movie_id(movie_id):
        return resp_json(400, {"error": True, "message": "api_key and movie_id required"})
    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None or not api_key_dict.get(ENABLED, True):
        return resp_json(401, {"error": True, "message": "invalid or disabled api_key"})
    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        return resp_json(401, {"error": True, "message": "invalid api_key"})
    try:
        odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    except odb.UnauthorizedUser:
        return resp_json(403, {"error": True, "message": "access denied"})
    except odb.InvalidMovie_Id:
        return resp_json(404, {"error": True, "message": "movie not found"})
    frame_urn = create_new_movie_frame(
        movie_id=movie_id, frame_number=frame_number, frame_data=frame_data
    )
    return resp_json(200, {"error": False, "frame_urn": frame_urn})


@app.get("/api/v1/ping")
def handle_ping() -> Dict[str, Any]:
    """Health check endpoint for Powertools router."""
    return {
        "error": False,
        "message": "ok",
        "now": time.time(),
    }


@app.get("/status")
@app.get("/prod/status")
def handle_status() -> Dict[str, Any]:
    """Status endpoint compatible with existing api_status helper."""
    return api_status()


@app.options("/api/v1")
def handle_options_api_v1() -> Dict[str, Any]:
    """CORS preflight for /api/v1."""
    # CORSConfig already injects most headers; return empty body.
    return {}


@app.post("/api/v1")
def handle_api_v1_root() -> Dict[str, Any]:
    """
    POST /api/v1 dispatcher based on JSON body 'action' field.
    Mirrors the legacy http_lambda_handler routing.
    """
    event = app.current_event.raw_event
    context = app.current_event.lambda_context
    payload = app.current_event.json_body or {}

    with _with_request_log_level(payload):
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
            return api_track_movie(payload, resp_json)
        if action == "new-frame":
            return api_new_frame(payload, resp_json)
        if action == "heartbeat":
            return api_heartbeat(event, context)
        if action == "log":
            return api_log()

        return resp_json(400, {"error": True, "message": f"Unknown action {action}"})


@app.get("/api/v1/frame")
def handle_get_frame() -> Dict[str, Any]:
    """GET /api/v1/frame delegate."""
    return api_get_frame(app.current_event.raw_event)


@app.get("/api/v1/movie-data")
def handle_get_movie_data() -> Dict[str, Any]:
    """GET /api/v1/movie-data delegate."""
    return api_get_movie_data(app.current_event.raw_event)


# Powertools-compatible Lambda entry point
lambda_handler = app.resolve
