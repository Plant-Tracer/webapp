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
import tempfile
import time
import urllib.parse
import uuid
from typing import Any, Dict, Tuple, Optional

import boto3

from .common import LOGGER
from .src.app import odb
from .src.app.odb import (
    DDBO,
    DATE_UPLOADED,
    TOTAL_BYTES,
)
from .src.app.mp4_metadata_lib import (
    RESEARCH_ANONYMOUS,
    RESEARCH_PROHIBITED,
    research_credit,
    set_comment,
)

__version__ = "0.1.0"

# Must match s3_presigned.UPLOAD_STAGING_PREFIX in main app
UPLOAD_STAGING_PREFIX = "uploads/"

# Special log_id for status ping; status API reads this to confirm Lambda received a set-status upload
LOG_ID_STATUS_PING = "lambda-status-ping"

################################################################
## S3 upload processing: move from staging to final key, update DynamoDB, set MP4 metadata
################################################################


def _s3_client():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION"))


def _comment_from_metadata(meta: Dict[str, str]) -> str:
    """Build MP4 comment string from S3 object metadata (x-amz-meta-*)."""
    research_use = (meta.get("research-use") or meta.get("research_use") or "0").strip()
    credit_by_name = (meta.get("credit-by-name") or meta.get("credit_by_name") or "0").strip()
    attribution = (meta.get("attribution-name") or meta.get("attribution_name") or "").strip()
    if research_use == "0":
        return RESEARCH_PROHIBITED
    if credit_by_name != "1" or not attribution:
        return RESEARCH_ANONYMOUS
    return research_credit(attribution)


def _process_upload_record(bucket: str, key: str) -> None:  # pylint: disable=too-many-locals,too-many-statements
    """
    Process one S3 object in the staging prefix: validate, apply MP4 metadata if video,
    copy to final key, update DynamoDB, delete staging object, log.
    """
    if not key.startswith(UPLOAD_STAGING_PREFIX):
        write_log(f"lambda-resize ignoring key (not under {UPLOAD_STAGING_PREFIX}): {key}")
        return

    suffix = key[len(UPLOAD_STAGING_PREFIX) :].strip("/")
    parts = suffix.split("/")
    if len(parts) != 2:
        write_log(f"lambda-resize invalid key format (expected uploads/course_id/movie_id.ext): {key}", course_id=None)
        return

    course_id, filename = parts[0], parts[1]
    base, ext = os.path.splitext(filename)
    if not base or not ext:
        write_log(f"lambda-resize invalid filename: {key}", course_id=course_id)
        return

    # JSON upload with action "set-status": write first 64 chars of message to logs and return (bootstrap ping test)
    if course_id == "_bootstrap" and ext.lower() == ".json":
        s3 = _s3_client()
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            payload = json.loads(body.decode("utf-8", "replace"))
            if (payload.get("action") or "").strip().lower() == "set-status":
                message = (payload.get("message") or "")[:64]
                ddbo = DDBO()
                ddbo.logs.put_item(
                    Item={
                        "log_id": LOG_ID_STATUS_PING,
                        "time_t": int(time.time()),
                        "message": message,
                    }
                )
                s3.delete_object(Bucket=bucket, Key=key)
                LOGGER.info("set-status processed key=%s message=%s", key, message)
                return
        except (json.JSONDecodeError, KeyError, Exception) as e:  # pylint: disable=broad-exception-caught
            LOGGER.warning("_bootstrap JSON handling failed: %s %s", key, e)
        # Not a valid set-status JSON; do not treat as movie
        return

    movie_id = base
    if not odb.is_movie_id(movie_id):
        write_log(f"lambda-resize invalid movie_id in key: {key}", course_id=course_id)
        return

    ddbo = DDBO()
    movie = ddbo.get_movie(movie_id)
    if not movie:
        write_log(f"lambda-resize movie not found: {movie_id} key={key}", course_id=course_id)
        return

    s3 = _s3_client()
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception as e:  # pylint: disable=broad-exception-caught
        write_log(f"lambda-resize head_object failed: {key} {e}", course_id=course_id)
        return

    content_type = head.get("ContentType", "")
    metadata = head.get("Metadata") or {}
    size = head.get("ContentLength", 0)

    final_key = f"{course_id}/{movie_id}{ext}"
    bucket_name = os.environ.get("PLANTTRACER_S3_BUCKET") or bucket
    final_urn = f"s3://{bucket_name}/{final_key}"

    is_video = ext.lower() in (".mp4", ".mov")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    if is_video:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            try:
                tmp.write(body)
                tmp.flush()
                comment = _comment_from_metadata(metadata)
                set_comment(tmp.name, comment)
                with open(tmp.name, "rb") as f:
                    body = f.read()
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

    s3.put_object(Bucket=bucket, Key=final_key, Body=body, ContentType=content_type, Metadata=metadata)
    s3.delete_object(Bucket=bucket, Key=key)

    odb.set_movie_data_urn(movie_id=movie_id, movie_data_urn=final_urn)
    ddbo.update_table(
        ddbo.movies,
        movie_id,
        {
            DATE_UPLOADED: int(time.time()),
            TOTAL_BYTES: size,
        },
    )

    write_log(
        f"lambda-resize processed {key} -> {final_key} movie_id={movie_id}",
        course_id=course_id,
    )
    LOGGER.info("Processed %s -> %s movie_id=%s", key, final_key, movie_id)


def handle_s3_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle S3 ObjectCreated notification; process each record."""
    records = event.get("Records") or []
    for record in records:
        if "s3" not in record:
            continue
        try:
            bucket = record["s3"]["bucket"]["name"]
            key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
            _process_upload_record(bucket, key)
        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("S3 record processing failed: %s", e)
            write_log(f"lambda-resize S3 processing error: {e}")

    return {"statusCode": 200, "body": ""}


################################################################
## Minimal support for a Python-based website in Lamda with jinja2 support
##

# jinja2

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
        "body": json.dumps(body),
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
    """Return 200 with status_message if a set-status upload was received (for bootstrap ping test)."""
    try:
        ddbo = DDBO()
        r = ddbo.logs.get_item(Key={"log_id": LOG_ID_STATUS_PING})
        item = r.get("Item")
        status_message = (item.get("message") or "") if item else None
        return resp_json(200, {"status": "ok", "status_message": status_message})
    except Exception as e:  # pylint: disable=broad-exception-caught
        LOGGER.exception("api_status failed: %s", e)
        return resp_json(500, {"status": "error", "message": str(e)})

################################################################
## main entry point from lambda system

# pylint: disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """Called by Lambda for HTTP API or S3 notifications."""
    if isinstance(event.get("Records"), list) and event["Records"] and "s3" in event["Records"][0]:
        return handle_s3_event(event)

    method, path, payload = parse_event(event)

    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # Status (GET; for bootstrap ping test)
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
