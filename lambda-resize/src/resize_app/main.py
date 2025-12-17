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
from typing import Any, Dict, Tuple, Optional

from .common import LOGGER
from .src.app.odb import DDBO

__version__ = "0.1.0"

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


def write_log( message, *, time_t=None, course_id=None, log_user_id=None, ipaddr=None):
    if time_t is None:
        time_t = time.time()

    ddbo = DDBO()
    ddbo.logs.put_item(Item={'log_id':uuid.uuid4(),
                             'time':time_t,
                             'user_id':log_user_id,
                             'ipaddr':ipaddr,
                             'course_id':course_id,
                             'message':message})

def api_ping(event, context):
    #write_log('ping')
    print("ping")
    return resp_json( 200,
                      { "error": False, "message": "ok", "path": sys.path,
                        "event" : str(event),
                        "context": str(context),
                        "environ": str(os.environ) } )

def api_log():
    #logs = odb.get_logs(user_id=None)
    logs="no logs today"
    return resp_json( 400, {"logs":logs})

################################################################
## main entry point from lambda system

# pylint: disable=too-many-return-statements, disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """called by lambda"""

    print("lambda_handler event=",event,"context=",context)
    for k,v in sorted(os.environ.items()):
        print(f"{k} = {v}")


    method, path, payload = parse_event(event)

    print("method=",method,"path=",path,"payload=",payload)

    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # JSON API Actions
                #
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
