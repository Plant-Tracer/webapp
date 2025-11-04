"""
Main entry point for AWS Lambda Dashboard

Generate the https://camera.planttracer.org/ home page.
Runs the camera.
"""

# at top of home_app/home.py (module import time)
from os.path import join,dirname
import base64
import binascii
import functools
import logging
import json
import os
import sys
import time
from typing import Any, Dict, Tuple, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .deploy.app import odb
from .deploy.app import db_object
from .deploy.app.constants import C

MY_DIR = dirname(__file__)
TEMPLATE_DIR = join(MY_DIR, "templates")
STATIC_DIR = join(MY_DIR, "static")

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
WEBSITE_DOMAIN = "camera.planttracer.com"
WEBSITE_URL = f"https://{WEBSITE_DOMAIN}"

# jinja2
env = Environment( loader=FileSystemLoader( [TEMPLATE_DIR]))

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


def resp_text( status: int, body: str,
               headers: Optional[Dict[str, str]] = None,
               cookies: Optional[list[str]] = None) -> Dict[str, Any]:
    """End HTTP event processing with text/html"""
    LOGGER.debug("resp_text(status=%s)", status)
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            **(headers or {}),
        },
        "body": body,
        "cookies": cookies or [],
    }


def resp_png( status: int, png_bytes: bytes,
              headers: Optional[Dict[str, str]] = None,
              cookies: Optional[list[str]] = None ) -> Dict[str, Any]:
    """End HTTP event processing with binary PNG"""
    LOGGER.debug("resp_png(status=%s, len=%s)", status, len(png_bytes))
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "image/png",
            "Access-Control-Allow-Origin": "*",
            **(headers or {}),
        },
        "body": base64.b64encode(png_bytes).decode("ascii"),
        "isBase64Encoded": True,
        "cookies": cookies or [],
    }


def redirect( location: str, extra_headers: Optional[dict] = None, cookies: Optional[list] = None) ->Dict[str, Any]:
    """End HTTP event processing with redirect to another website"""
    LOGGER.debug("redirect(%s,%s,%s)", location, extra_headers, cookies)
    headers = {"Location": location}
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": 302, "headers": headers, "cookies": cookies or [], "body": ""}


def error_404(page) -> Dict[str, Any]:
    """Generate an error"""
    template = env.get_template("404.html")
    return resp_text(404, template.render(page=page))


def render_template(page="index.html", **kwargs)  -> Dict[str, Any]:
    """generic template handler"""

    try:
        template = env.get_template(page)
        return resp_text(200, template.render(**kwargs))
    except TemplateNotFound:
        return error_404(page)


def static_file(fname)  -> Dict[str, Any]:
    """Serve a static file"""
    if ("/" in fname) or (".." in fname) or ("\\" in fname):
        # path transversal attack?
        return error_404(fname)
    headers = {}
    try:
        if fname.endswith(".png"):
            with open(join(STATIC_DIR, fname), "rb") as f:
                return resp_png(200, f.read())

        with open(join(STATIC_DIR, fname), "r", encoding="utf-8") as f:
            if fname.endswith(".css"):
                headers["Content-Type"] = "text/css; charset=utf-8"
            return resp_text(200, f.read(), headers=headers)
    except FileNotFoundError:
        return error_404(fname)


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


def api_camera_start(event, context, payload)  -> Dict[str, Any]:
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

    LOGGER.info("api_camera event=%s context=%s payload=%s", event, context, payload)
    user = odb.validate_api_key(payload.get(odb.API_KEY, ""))
    if not user:
        return resp_json(200, {"message": "api_key not provided or invalid"})

    movie_id = payload.get(odb.MOVIE_ID)
    if movie_id is None:
        # Get a new movie_id
        movie_id = odb.create_new_movie(user_id=user[odb.USER_ID],
                                        description='Upload started '+time.asctime())

    # Generate the URLs
    start = payload['start']
    count = payload['count']
    object_names = [db_object.object_name(course_id = user[odb.PRIMARY_COURSE_ID],
                                          movie_id = movie_id,
                                          frame_number = frame_number, ext=C.JPEG_EXTENSION)
                    for frame_number in range(start,count)]

    object_urns = [db_object.make_urn(object_name=name) for name in object_names]
    signed_urls = [db_object.make_signed_url(urn=urn) for urn in object_urns]
    return resp_json(200, {'signed_urls':signed_urls, 'start':start})

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


################################################################
## main entry point from lambda system


# pylint: disable=too-many-return-statements, disable=too-many-branches, disable=unused-argument
def lambda_handler(event, context) -> Dict[str, Any]:
    """called by lambda"""

    print("now running import deploy")
    print("cwd=",os.getcwd())


    method, path, payload = parse_event(event)

    # Detect if this is a browser request vs API request
    accept_header = event.get("headers", {}).get("accept", "")
    is_browser_request = "text/html" in accept_header
    with _with_request_log_level(payload):
        try:
            LOGGER.info( "req method='%s' path='%s' action='%s'", method, path, payload.get("action") )
            action = (payload.get("action") or "").lower()

            match (method, path, action):
                ################################################################
                # JSON API Actions
                #
                case ("POST", "/api/v1", "ping"):
                    return resp_json( 200,
                                      { "error": False, "message": "ok", "path": sys.path, "context": dict(context),
                                        "environ": dict(os.environ) } )

                case ("POST", "/api/v1", "camera-start"):
                    return api_camera_start(event, context, payload)

                case ("POST", "/api/v1", "heartbeat"):
                    return api_heartbeat(event, context)

                case ("POST", "/api/v1", _):
                    return resp_json( 400, { "error": True, "message": f"Unknown action {action}"})

                ################################################################
                # Human actions
                case ("GET", "/", _):
                    return render_template("index.html")

                case ("GET", "/about", _):
                    return render_template("about.html")

                # This must be last - catch all GETs, check for /static
                # used for serving css and javascript
                case ("GET", p, _):
                    if p.startswith("/static"):
                        return static_file(p.removeprefix("/static/"))
                    return error_404(p)

                ################################################################
                # error
                case (_, _, _):
                    return error_404(path)

        except Exception as e:  # pylint: disable=broad-exception-caught
            LOGGER.exception("Unhandled exception! e=%s", e)

            if is_browser_request:
                # Return HTML error page for browser requests
                template = env.get_template("error_generic.html")
                return resp_text(500, template.render(error_message=str(e)))

            # Return JSON for API requests
            return resp_json(500, {"error": True, "message": str(e)})
