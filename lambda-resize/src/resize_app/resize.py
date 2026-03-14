"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

import base64
import io
import json
import os
import sys
import time
import urllib.parse
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

from .common import LOGGER
from .movie_metadata import extract_movie_metadata
from .rotate_zip import (
    extract_single_frame,
    resize_jpeg_to_fit,
    rotate_video_av,
    video_frames_to_zip_av,
)
from .src.app import odb
from .src.app.constants import C
from .src.app.odb import (
    DDBO,
    ENABLED,
    MOVIE_DATA_URN,
    TOTAL_BYTES,
    FPS,
    WIDTH,
    HEIGHT,
    TOTAL_FRAMES,
    USER_ID,
)

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


def resp_redirect(location: str, status: int = 302) -> Dict[str, Any]:
    """Return HTTP redirect response (e.g. for get-movie-data)."""
    return {
        "statusCode": status,
        "headers": {
            "Location": location,
            "Access-Control-Allow-Origin": "*",
        },
        "body": "",
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


def _s3_client():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION"))


def api_start_processing(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called after the client uploads the movie to the final S3 key. Verify the object
    exists, then set date_uploaded, total_bytes, and processing_state so the VM can
    serve get-movie-data. get-frame is implemented in this Lambda (api/v1/frame).
    """
    movie_id = (payload.get("movie_id") or "").strip()
    if not odb.is_movie_id(movie_id):
        return resp_json(400, {"error": True, "message": "movie_id missing or invalid"})
    ddbo = DDBO()
    try:
        movie = ddbo.get_movie(movie_id)
    except odb.InvalidMovie_Id:
        return resp_json(404, {"error": True, "message": "movie not found"})
    urn = movie.get(MOVIE_DATA_URN)
    if not urn or not urn.strip():
        return resp_json(400, {"error": True, "message": "movie has no movie_data_urn"})
    parsed = urllib.parse.urlparse(urn)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        return resp_json(400, {"error": True, "message": "invalid movie_data_urn"})
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    s3 = _s3_client()
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.warning("start_processing head_object failed: %s %s %s", bucket, key, e)
        return resp_json(503, {"error": True, "message": "object not found in S3; upload may not have completed"})
    size = head.get("ContentLength", 0)
    ddbo.update_table(
        ddbo.movies,
        movie_id,
        {
            # date_uploaded is set when upload starts; here we just record size and mark processing.
            TOTAL_BYTES: size,
            "processing_state": "processing",
        },
    )
    write_log(f"start_processing movie_id={movie_id} size={size}", course_id=movie.get("course_id"))
    LOGGER.info("start_processing movie_id=%s size=%s", movie_id, size)
    return resp_json(200, {"error": False, "started": True, "movie_id": movie_id})


def api_rotate_and_zip(payload: Dict[str, Any]) -> Dict[str, Any]:  # pylint: disable=too-many-branches
    """
    Rotate movie by N×90° (N=1..3) and build frame zip. Uses PyAV + Pillow only (no ffmpeg).
    Downloads movie from S3, rotates, uploads back, builds zip, uploads zip, updates DDB.
    """
    movie_id = (payload.get("movie_id") or "").strip()
    if not odb.is_movie_id(movie_id):
        return resp_json(400, {"error": True, "message": "movie_id missing or invalid"})
    try:
        steps = int(payload.get("rotation_steps", 1))
    except (TypeError, ValueError):
        steps = 1
    # Allow 0 = zip-only (no rotation); 1–3 = rotate then zip.
    steps = max(0, min(3, steps))

    ddbo = DDBO()
    try:
        movie = ddbo.get_movie(movie_id)
    except odb.InvalidMovie_Id:
        return resp_json(404, {"error": True, "message": "movie not found"})
    urn = movie.get(MOVIE_DATA_URN)
    if not urn or not urn.strip():
        return resp_json(400, {"error": True, "message": "movie has no movie_data_urn"})
    parsed = urllib.parse.urlparse(urn)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        return resp_json(400, {"error": True, "message": "invalid movie_data_urn"})
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    course_id = movie.get("course_id") or ""
    s3 = _s3_client()

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        data = obj["Body"].read()
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.warning("rotate_and_zip get_object failed: %s %s %s", bucket, key, e)
        return resp_json(503, {"error": True, "message": "failed to download movie from S3"})

    # If steps == 0, skip rotation and keep original bytes; otherwise rotate and overwrite movie.
    if steps > 0:
        try:
            rotated = rotate_video_av(data, steps)
        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("rotate_video_av failed: %s", e)
            return resp_json(500, {"error": True, "message": "rotation failed"})

        try:
            s3.put_object(Bucket=bucket, Key=key, Body=rotated, ContentType="video/mp4")
        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.warning("rotate_and_zip put_object (movie) failed: %s", e)
            return resp_json(503, {"error": True, "message": "failed to upload rotated movie"})

        ddbo.update_table(
            ddbo.movies,
            movie_id,
            {TOTAL_BYTES: len(rotated), "processing_state": "processing"},
        )
        movie_bytes_for_zip = rotated
    else:
        # No rotation requested; use original bytes but still build zip.
        movie_bytes_for_zip = data
        ddbo.update_table(
            ddbo.movies,
            movie_id,
            {"processing_state": "processing"},
        )

    def _zip_progress(current: int, total: int) -> None:
        """Best-effort progress updates in DynamoDB; safe to fail silently."""
        # Only write every 5 frames (and always for the final frame) to avoid excessive writes.
        if total <= 0:
            return
        if current % 5 != 0 and current != total:
            return
        try:
            ddbo.update_table(
                ddbo.movies,
                movie_id,
                {
                    "zip_frame_processing": {
                        "total": int(total),
                        "current": int(current),
                    },
                    "processing_state": "processing-zip",
                },
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.debug("zip progress update failed for %s: %s", movie_id, exc)

    try:
        zip_bytes = video_frames_to_zip_av(
            movie_bytes_for_zip,
            progress_cb=_zip_progress,
            target_wh=(C.ANALYSIS_FRAME_MAX_WIDTH, C.ANALYSIS_FRAME_MAX_HEIGHT),
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.exception("video_frames_to_zip_av failed: %s", e)
        return resp_json(500, {"error": True, "message": "zip build failed"})

    zip_key = f"{course_id}/{movie_id}{C.ZIP_MOVIE_EXTENSION}"
    zip_urn = f"s3://{bucket}/{zip_key}"
    try:
        s3.put_object(
            Bucket=bucket,
            Key=zip_key,
            Body=zip_bytes,
            ContentType="application/zip",
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.warning("rotate_and_zip put_object (zip) failed: %s", e)
        return resp_json(503, {"error": True, "message": "failed to upload zip"})

    # Final state: zip finished, mark ready, and write full metadata from the movie we used (rotated or not).
    meta = extract_movie_metadata(movie_bytes_for_zip)
    update_payload = {
        "movie_zipfile_urn": zip_urn,
        "processing_state": "ready",
    }
    for key, attr in (("width", WIDTH), ("height", HEIGHT), ("fps", FPS), ("total_frames", TOTAL_FRAMES), ("total_bytes", TOTAL_BYTES)):
        if key in meta and meta[key] is not None:
            update_payload[attr] = meta[key]
    try:
        ddbo.update_table(ddbo.movies, movie_id, update_payload)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOGGER.debug("final zip state update failed for %s: %s", movie_id, exc)
    write_log(f"rotate_and_zip movie_id={movie_id} steps={steps}", course_id=course_id)
    LOGGER.info("rotate_and_zip movie_id=%s steps=%s", movie_id, steps)
    return resp_json(200, {"error": False, "movie_id": movie_id, "rotation_steps": steps})


def api_get_frame(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    GET /api/v1/frame: return a single frame as JPEG. Query params: api_key, movie_id, frame_number, size (optional, 'analysis' = resize to analysis size).
    Authenticates via api_key, fetches movie from S3, extracts frame with PyAV, optionally resizes and updates width/height for frame 0.
    """
    params = event.get("queryStringParameters") or event.get("query_params") or {}
    api_key = (params.get("api_key") or "").strip()
    movie_id = (params.get("movie_id") or "").strip()
    try:
        frame_number = int(params.get("frame_number", 0))
    except (TypeError, ValueError):
        frame_number = 0
    size_val = (params.get("size") or "").strip().lower()
    size_analysis = size_val == "analysis"

    if not api_key or not odb.is_movie_id(movie_id):
        return resp_json(400, {"error": True, "message": "api_key and movie_id required"})
    if frame_number < 0:
        return resp_json(400, {"error": True, "message": "invalid frame_number"})

    ddbo = DDBO()
    api_key_dict = ddbo.get_api_key_dict(api_key)
    if api_key_dict is None or not api_key_dict.get(ENABLED, True):
        return resp_json(401, {"error": True, "message": "invalid or disabled api_key"})
    user_id = api_key_dict.get(USER_ID)
    if not user_id:
        return resp_json(401, {"error": True, "message": "invalid api_key"})
    try:
        user = ddbo.get_user(user_id)
        if not user.get(ENABLED, True):
            return resp_json(401, {"error": True, "message": "user disabled"})
    except Exception:  # pylint: disable=broad-exception-caught
        return resp_json(401, {"error": True, "message": "user not found"})
    try:
        movie = odb.can_access_movie(user_id=user_id, movie_id=movie_id)
    except odb.UnauthorizedUser:
        return resp_json(403, {"error": True, "message": "access denied"})
    except odb.InvalidMovie_Id:
        return resp_json(404, {"error": True, "message": "movie not found"})

    urn = movie.get(MOVIE_DATA_URN)
    if not urn or not urn.strip():
        return resp_json(503, {"error": True, "message": "Movie still processing. Retry in a few seconds."})

    parsed = urllib.parse.urlparse(urn)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        return resp_json(400, {"error": True, "message": "invalid movie_data_urn"})
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    s3 = _s3_client()
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        movie_bytes = obj["Body"].read()
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.warning("get_frame get_object failed: %s %s %s", bucket, key, e)
        return resp_json(503, {"error": True, "message": "failed to load movie from S3"})

    try:
        jpeg_bytes = extract_single_frame(movie_bytes, frame_number)
    except ValueError as e:
        return resp_json(400, {"error": True, "message": str(e)})

    if size_analysis:
        jpeg_bytes = resize_jpeg_to_fit(
            jpeg_bytes,
            getattr(C, "ANALYSIS_FRAME_MAX_WIDTH", 640),
            getattr(C, "ANALYSIS_FRAME_MAX_HEIGHT", 480),
        )

    # Update stored width/height from first frame when missing (so analyze page has dimensions).
    if frame_number == 0 and (not movie.get(WIDTH) or not movie.get(HEIGHT)):
        try:
            from PIL import Image  # pylint: disable=import-outside-toplevel
            img = Image.open(io.BytesIO(jpeg_bytes))
            img.load()
            w, h = img.size
            if w and h:
                odb.set_metadata(user_id=user_id, set_movie_id=movie_id, prop=WIDTH, value=w)
                odb.set_metadata(user_id=user_id, set_movie_id=movie_id, prop=HEIGHT, value=h)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOGGER.debug("get_frame set_metadata failed: %s", exc)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "image/jpeg", "Access-Control-Allow-Origin": "*"},
        "body": base64.b64encode(jpeg_bytes).decode("ascii"),
        "isBase64Encoded": True,
    }


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

