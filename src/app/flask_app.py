"""
Main Flask application for planttracer.
"""

# pylint: disable=too-many-lines

import sys
import os
import time
import traceback
import logging

from flask import Flask, request, render_template, jsonify, make_response, Response, redirect
from werkzeug.exceptions import NotFound
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix


# Bottle creates a large number of no-member errors, so we just remove the warning
# pylint: disable=no-member
from . import apikey

from .flask_api import api_bp
from .constants import __version__, GET, GET_POST, C, log_level, logger
from .auth import AuthError
from .apikey import cookie_name, page_dict
from .odb import InvalidAPI_Key, InvalidUser_Email
from . import config_check

DEFAULT_OFFSET = 0
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""
LOAD_MESSAGE = "Error: JavaScript did not execute. Please open JavaScript console and report a bug."
CACHE_MAX_AGE = 5               # for debugging; change to 360 for production

################################################################
# Initialization Code

def fix_boto_log_level() -> None:
    """Do not run boto loggers at debug level"""
    logging.getLogger('boto').setLevel(logging.INFO)
    logging.getLogger('boto3').setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.INFO)


################################################################
## API SUPPORT


# Use instrumented static files in test mode for coverage collection
static_folder = 'static'
if os.environ.get('COLLECT_JS_COVERAGE', '').lower() in ('1', 'true', 'yes'):
    instrumented_static = os.path.join(os.path.dirname(__file__), 'static-instrumented')
    if os.path.exists(instrumented_static):
        static_folder = 'static-instrumented'
        logger.info("Using instrumented static files from static-instrumented/ for JS coverage")

app = Flask(__name__, static_folder=static_folder, static_url_path='/static')

# Tell Flask to trust the X-Forwarded headers from Nginx
# x_for=1 (IP), x_proto=1 (HTTP/HTTPS), x_host=1 (Host header)
if os.environ.get('DISABLE_PROXYFIX', '').lower() not in ('1', 'true', 'yes'):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.register_blueprint(api_bp, url_prefix='/api')

logging.basicConfig(format=C.LOGGING_CONFIG, level=log_level, force=True)
app.logger.setLevel(log_level)
fix_boto_log_level()



################################################################
### Error Handling. An exception automatically generates this response.
################################################################

@app.errorhandler(NotFound)
def not_found(e: NotFound) -> tuple[str, int]:
    """Handle 404 Not Found errors."""
    return f"<h1>404 Not Found</h1><pre>\n{e}\n</pre>", 404

@app.errorhandler(AuthError)
def handle_auth_error(ex: AuthError) -> Response:
    """Raise AuthError('message') will result in a JSON response:
    {'message':message, 'error':True}
    as defined in auth.AuthError
    """
    logger.info("handle_auth_error(%s)", ex)
    response = jsonify(ex.to_dict())
    response.status_code = ex.status_code
    return response

@app.errorhandler(InvalidAPI_Key)
def handle_apikey_error(ex: InvalidAPI_Key) -> Response:
    """Handle invalid API key: clear cookie and redirect to logout page."""
    app.logger.error("InvalidAPI_Key: %s %s", ex, type(ex))
    resp = make_response(redirect('/logout'))
    resp.set_cookie(cookie_name(), '', expires=0, path='/')
    return resp

@app.errorhandler(Exception)
def handle_exception(e: Exception) -> HTTPException | tuple[Response, int]:
    """Handle unhandled exceptions."""
    if isinstance(e, HTTPException):
        return e  # Let Flask handle it or route it to its specific handler
    logger.exception("Unhandled exception")
    return jsonify({"error": True, "message": "Internal Server Error"}), 500

@app.errorhandler(InvalidUser_Email)
def handle_email_error(e: InvalidUser_Email) -> tuple[str, int]:
    """Handle invalid user email errors."""
    return f"<h1>Invalid User</h1><p>That email address does not exist in the database {e}</p>", 400


################################################################
# Configuration error page (no DB access — use minimal context)
################################################################

# Cache for config check results; avoid hitting S3/DynamoDB on every request
_CONFIG_CHECK_CACHE = {}
_CONFIG_CHECK_TTL = 60  # seconds


def _config_error_page_context(error_title: str, error_message: str):
    """Build template context for config_error.html without touching the DB."""
    ret = {
        C.API_BASE: apikey.api_base,
        C.STATIC_BASE: apikey.static_base,
        'favicon_base64': apikey.favicon_base64(),
        'api_key': None,
        'user_id': None,
        'user_name': None,
        'user_email': None,
        'logged_in': 0,
        'demo_mode': apikey.in_demo_mode(),
        'admin': 0,
        'user_primary_course_id': None,
        'primary_course_name': None,
        'title': 'Plant Tracer Configuration Error',
        'hostname': request.host,
        'movie_id': 0,
        'MAX_FILE_UPLOAD': C.MAX_FILE_UPLOAD,
        'version': __version__,
        'git_head_time': apikey.git_head_time(),
        'git_last_commit': apikey.git_last_commit(),
        'git_branch': apikey.git_branch(),
        'message': error_message,
        'error_title': error_title,
        'error_message': error_message,
    }
    for (k, v) in list(ret.items()):
        if v is None:
            ret[k] = "null"
    return ret


def _run_config_checks():
    """Run DynamoDB, S3 CORS, and S3 bucket region checks; return (d_ok, d_msg, c_ok, c_msg, r_ok, r_msg)."""
    now = time.monotonic()
    cached = _CONFIG_CHECK_CACHE.get("result")
    if cached is not None and (now - _CONFIG_CHECK_CACHE.get("ts", 0)) < _CONFIG_CHECK_TTL:
        return cached
    d_ok, d_msg = config_check.check_dynamodb()
    origin = f"{request.scheme}://{request.host}"
    c_ok, c_msg = config_check.check_s3_cors(origin)
    r_ok, r_msg = config_check.check_s3_bucket_region()
    _CONFIG_CHECK_CACHE["result"] = (d_ok, d_msg, c_ok, c_msg, r_ok, r_msg)
    _CONFIG_CHECK_CACHE["ts"] = now
    _CONFIG_CHECK_CACHE["d_msg"] = d_msg
    _CONFIG_CHECK_CACHE["c_msg"] = c_msg
    _CONFIG_CHECK_CACHE["r_msg"] = r_msg
    return (d_ok, d_msg, c_ok, c_msg, r_ok, r_msg)


@app.before_request
def _before_request_config_check():
    """If DynamoDB, S3 CORS, or S3 bucket region is broken, redirect to the configuration error page."""
    path = request.path
    if path == "/config-error" or path.startswith("/static/") or path.startswith("/api/"):
        return None
    if path in ("/ping", "/ver", "/health"):
        return None
    try:
        d_ok, _, c_ok, _, r_ok, _ = _run_config_checks()
        if not d_ok:
            return redirect("/config-error?reason=dynamodb")
        if not c_ok:
            return redirect("/config-error?reason=cors")
        if not r_ok:
            return redirect("/config-error?reason=region")
    except Exception:  # pylint: disable=broad-exception-caught
        # Do not block the app if the check itself fails (e.g. import error)
        pass
    return None


@app.route('/config-error', methods=GET)
def func_config_error():
    """Serve the configuration error page (e.g. CORS or DynamoDB misconfigured)."""
    reason = request.args.get("reason", "unknown").lower()
    custom_message = request.args.get("message", "").strip()
    if reason == "dynamodb":
        error_title = "Database unreachable"
        error_message = (
            "The application cannot reach the DynamoDB database. "
            "Check AWS credentials, network, and DYNAMODB_TABLE_PREFIX."
        )
        last_msg = _CONFIG_CHECK_CACHE.get("d_msg")
        if last_msg:
            error_message += f" Details: {last_msg}"
        if custom_message:
            error_message += f" {custom_message}"
    elif reason == "cors":
        error_title = "S3 CORS misconfigured"
        error_message = (
            "The S3 bucket CORS policy does not allow this site to load or upload movie data. "
            "Run on the server: poetry run python -m app.s3_presigned <bucket>"
        )
        last_msg = _CONFIG_CHECK_CACHE.get("c_msg")
        if last_msg:
            error_message += f" Details: {last_msg}"
        if custom_message:
            error_message += f" {custom_message}"
    elif reason == "region":
        error_title = "S3 bucket region mismatch"
        error_message = (
            "The S3 bucket is in a different region than the app (AWS_REGION). "
            "Browser uploads will fail with connection reset. Set AWS_REGION to the bucket's region."
        )
        last_msg = _CONFIG_CHECK_CACHE.get("r_msg")
        if last_msg:
            error_message += f" Details: {last_msg}"
        if custom_message:
            error_message += f" {custom_message}"
    else:
        error_title = "Configuration error"
        error_message = custom_message or "A configuration problem prevents this app from running correctly."
    return render_template(
        "config_error.html",
        **_config_error_page_context(error_title, error_message),
    )


################################################################
# HTML Pages served with template system
################################################################

################
## These mostly do forms or static content

@app.route('/', methods=GET)
def func_root() -> str | tuple[str, int]:
    """/ - serve the home page"""
    try:
        return render_template('index.html', **page_dict())
    except Exception as ex:     # pylint: disable=broad-exception-caught
        return f"<h1>500 Exception:</h1><pre>\n{ex}\n{traceback.print_exception(ex)}</pre>", 500


@app.route('/about', methods=GET)
def func_about() -> str:
    """Serve the about page."""
    return render_template('about.html', **page_dict('About'))

@app.route('/error', methods=GET)
def func_error() -> str:
    """Serve the error page."""
    return render_template('error.html', **page_dict('Error', lookup=False))

@app.route('/audit', methods=GET)
def func_audit() -> str:
    """Serve the audit page."""
    return render_template('audit.html', **page_dict("Audit", require_auth=True))

@app.route('/analyze', methods=GET)
def func_analyze() -> str:
    """Serve the analyze page."""
    return render_template('analyze.html', **page_dict('Analyze Movie', require_auth=True))

##
## Login page includes the api keys of all the demo users.
##
@app.route('/login', methods=GET_POST)
def func_login():
    return render_template('login.html', **page_dict('Login'))

@app.route('/logout', methods=GET_POST)
def func_logout():
    resp = make_response(render_template('logout.html', **page_dict('Logout',logout=True)))
    resp.set_cookie(cookie_name(), '', expires=0)
    return resp

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "message": "pong"})

@app.route('/privacy', methods=GET)
def func_privacy():
    return render_template('privacy.html', **page_dict('Privacy'))

@app.route('/register', methods=GET)
def func_register():
    """/register sends the register.html template which loads register.js with register variable set to True
     Note: register and resend both need the endpint so that they can post it to the server
     for inclusion in the email. This is the only place where the endpoint needs to be explicitly included.
    """
    return render_template('register.html',
                           title='Plant Tracer Registration Page',
                           hostname=request.host,
                           register=True)

@app.route('/resend', methods=GET)
def func_resend():
    """/resend sends the register.html template which loads register.js with register variable set to False"""
    return render_template('register.html',
                           title='Plant Tracer Resend Registration Link',
                           hostname = request.host,
                           register=False)

@app.route('/tos', methods=GET)
def func_tos():
    return render_template('tos.html', **page_dict('Terms of Service'))

@app.route('/users', methods=GET)
def func_users():
    """/users - provide a users list"""
    return render_template('users.html', **page_dict('List Users', require_auth=True))

################
# These are the two links that might have an ?apikey=; if we got that, set the cookie
@app.route('/list', methods=GET)
def func_list():
    response = make_response(render_template('list.html',
                                             **page_dict('List Movies',
                                                         require_auth=True)))
    # if api_key was in the query string, set the cookie
    apikey.add_cookie(response)
    return response

@app.route('/upload', methods=GET)
def func_upload():
    """/upload - Upload a new file. Can also set cookie (because of /upload link that is sent)."""
    logger.debug("/upload require_auth=True")
    response = make_response(render_template('upload.html',
                                         **page_dict('Upload a Movie',
                                                     require_auth=True)))
    apikey.add_cookie(response)
    return response

################################################################
## debug/demo

@app.route('/debug', methods=GET)
def app_debug():
    python_keys = {"path":sys.path,
                   "sys.version":sys.version}
    return render_template('debug.html', routes=app.url_map, python_keys = python_keys, environ=os.environ)

@app.route('/demo_tracer1.html', methods=GET)
def demo_tracer1():
    return render_template('demo_tracer1.html', **page_dict('demo_tracer1',require_auth=False))

@app.route('/demo_tracer2.html', methods=GET)
def demo_tracer2():
    return render_template('demo_tracer2.html', **page_dict('demo_tracer2',require_auth=False))

@app.route('/demo_tracer3.html', methods=GET)
def demo_tracer3():
    return render_template('demo_tracer3.html', **page_dict('demo_tracer3',require_auth=False))

@app.route('/ver', methods=GET_POST)
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    app.logger.info("/ver")
    response = make_response(render_template('version.txt',
                                             __version__=__version__,
                                             sys_version= sys.version))
    response.headers['Content-Type'] = 'text/plain'
    return response

################################################################
## Finally, if we are running under flask, run this.
