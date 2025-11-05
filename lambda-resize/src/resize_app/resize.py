"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
from os.path import dirname
import base64
import binascii
import functools
import logging
import json
import os
import sys
import time
from typing import Any, Dict, Tuple, Optional



MY_DIR = dirname(__file__)

__version__ = "0.1.0"

################################################################
### Logger
@functools.cache  # singleton
def _configure_root_once():
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Configure a dedicated app logger; avoid touching the root logger.
    app_logger = logging.getLogger("e11")
    app_logger.setLevel(level)

    if not app_logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s %(levelname)s [%(name)s %(filename)s:%(lineno)d %(funcName)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        app_logger.addHandler(handler)

    # Prevent bubbling to root (stops double logs)
    app_logger.propagate = False

    # If this code is used as a library elsewhere, avoid “No handler” warnings:
    logging.getLogger(__name__).addHandler(logging.NullHandler())


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger under the 'e11' namespace (e.g., e11.grader)."""
    _configure_root_once()
    return logging.getLogger("e11" + ("" if not name else f".{name}"))


LOGGER = get_logger("grader")

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


def do_ping():
    return resp_json( 200,
                      { "error": False, "message": "ok", "path": sys.path, "context": dict(context),
                        "environ": dict(os.environ) } )

def api_log(event,context):
    return resp_json( 400, {"message":"Log not yet implemented"})

################################################################
## main entry point from lambda system

# pylint: disable=too-many-return-statements, disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """called by lambda"""

    method, path, payload = parse_event(event)

    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # JSON API Actions
                #
                case (_, "/api/v1", "ping"):
                    return do_ping()

                case (_, '/api/v1/ping', _):
                    return do_ping()

                case ("POST", "/api/v1", "resize-start"):
                    return api_resize(event, context, payload)

                case ("POST", "/api/v1", "heartbeat"):
                    return api_heartbeat(event, context)

                case ("POST", "/api/v1", "log"):
                    return api_log(event, context)

                case ("POST", "/api/v1", _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

                ################################################################
                # error
                case (_, _, _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("Unhandled exception! e=%s", e)

            # Return JSON for API requests
            return resp_json(500, {"error": True, "message": str(e)})
