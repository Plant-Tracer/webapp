"""
Lambda HTTP API entry point. Parses the event and delegates to resize API handlers.
"""

import base64
import binascii
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import boto3

from .lambda_tracking_env import LambdaTrackingEnv
from .resize import (  # pylint: disable=wrong-import-order
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
    _with_request_log_level,
)
from .src.app import odb
from .src.app.odb import (
    DDBO,
    USER_ID,
    ENABLED,
    MOVIE_DATA_URN,
    MOVIE_ZIPFILE_URN,
)
from .src.app.odb_movie_data import create_new_movie_frame, get_movie_data
from .src.app.s3_presigned import make_signed_url, object_exists

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


def api_track_movie(payload: Dict[str, Any], resp_json: Any) -> Dict[str, Any]:
    """
    POST /api/v1 with action=track-movie. Body: api_key, movie_id, frame_start.
    Authorizes via api_key (same as get-frame), then enqueues tracking work to SQS.
    Refuses to start if this movie is already tracking and status was updated <1 hour ago.
    """

    api_key = (payload.get("api_key") or "").strip()
    movie_id = (payload.get("movie_id") or "").strip()
    try:
        frame_start = int(payload.get("frame_start", 0))
    except (TypeError, ValueError):
        frame_start = 0
    if frame_start < 0 or frame_start >= 10000:
        return resp_json(400, {"error": True, "message": "frame_start must be between 0 and 9999"})
    if not api_key or not movie_id:
        return resp_json(400, {"error": True, "message": "api_key and movie_id required"})
    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None or not api_key_dict.get(ENABLED, True):
        return resp_json(401, {"error": True, "message": "invalid or disabled api_key"})
    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        return resp_json(401, {"error": True, "message": "invalid api_key"})
    env = LambdaTrackingEnv()
    if not env.try_claim_tracking(movie_id):
        return resp_json(
            409,
            {
                "error": True,
                "message": "Tracking already in progress for this movie. Wait for it to finish or try again in an hour.",
            },
        )

    queue_url = os.environ.get("TRACKING_QUEUE_URL", "").strip()
    if not queue_url:
        return resp_json(500, {"error": True, "message": "TRACKING_QUEUE_URL not configured"})

    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION"))
    body = {
        "user_id": user_id,
        "movie_id": movie_id,
        "frame_start": frame_start,
        "origin_start": frame_start,
        "batch_size": max(1, min(int(payload.get("batch_size", 1)) or 1, 500)),
    }
    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))
    return resp_json(
        202,
        {
            "error": False,
            "accepted": True,
            "movie_id": movie_id,
            "frame_start": frame_start,
            "batch_size": body["batch_size"],
        },
    )


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

    if format_json:
        data_urn = movie.get(MOVIE_DATA_URN)
        zip_urn = movie.get(MOVIE_ZIPFILE_URN)
        if not data_urn:
            return resp_json(503, {"error": True, "message": "Movie not ready (no URN)."})
        if not object_exists(data_urn):
            return resp_json(
                503,
                {"error": True, "message": "Movie still processing (upload not yet at final key). Retry in a few seconds."},
                headers={"Retry-After": "5"},
            )
        body = {
            "movie_id": movie_id,
            "url": make_signed_url(urn=data_urn),
            "zip_url": make_signed_url(urn=zip_urn) if zip_urn and object_exists(zip_urn) else None,
        }
        return resp_json(200, body)

    data_urn = get_movie_data(movie_id=movie["movie_id"], zipfile=zipfile, get_urn=True)
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


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Called by Lambda for HTTP API requests (no S3 event invocation)."""

    method, path, payload = parse_event(event)

    # Record Lambda invocation start in DynamoDB logs.
    ddbo = DDBO()
    request_id = getattr(context, "aws_request_id", "unknown")
    log_id = f"resize-lambda:{request_id}"
    start_ts = time.time()
    start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat()
    ddbo.update_table(
        ddbo.logs,
        log_id,
        {
            "start_time": int(start_ts),
            "sk": start_iso,
        },
    )

    with _with_request_log_level(payload):
        try:
            action = (payload.get("action") or "").lower()
            from .common import LOGGER  # pylint: disable=import-outside-toplevel

            # Enrich DynamoDB log entry with request metadata.
            ddbo.update_table(
                ddbo.logs,
                log_id,
                {
                    "method": method,
                    "path": path,
                    "action": action,
                    "params": payload,
                },
            )

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

                case ("POST", "/api/v1", "track-movie"):
                    return api_track_movie(payload, resp_json)

                case ("POST", "/api/v1", "new-frame"):
                    return api_new_frame(payload, resp_json)

                case ("GET", "/api/v1/frame", _):
                    return api_get_frame(event)

                case ("GET", "/api/v1/movie-data", _):
                    return api_get_movie_data(event)

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
            ddbo.update_table(
                ddbo.logs,
                log_id,
                {"elapsed_time": time.time() - start_ts},
            )
            return resp_json(500, {"error": True, "message": str(e)})

        ddbo.update_table(
            ddbo.logs,
            log_id,
            {"elapsed_time": time.time() - start_ts},
        )
