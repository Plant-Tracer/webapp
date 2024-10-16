"""
WSGI file used for bottle interface.

The goal is to only have the bottle code in this file and nowhere else.

Debug on Dreamhost:
(cd ~/apps.digitalcorpora.org/;make touch)
https://downloads.digitalcorpora.org/
https://downloads.digitalcorpora.org/ver
https://downloads.digitalcorpora.org/reports

Debug locally:

$ python bottle_app.py
Bottle v0.12.23 server starting up (using WSGIRefServer())...
Listening on http://localhost:8080/
Hit Ctrl-C to quit.

Then go to the URL printed above (e.g. http://localhost:8080). Note that you must have the environment variables set:
export MYSQL_DATABASE=***
export MYSQL_HOST=***
export MYSQL_PASSWORD=***
export MYSQL_USER=***
export SMTP_HOST=***
export SMTP_PASSWORD=***
export SMTP_PORT=***
export SMTP_USERNAME=***

For testing, you must also set:
export IMAP_PASSWORD=****
export IMAP_SERVER=****
export IMAP_USERNAME=****
export TEST_ENDPOINT='http://localhost:8080' (or whatever it is above)

For automated tests, we are using the localmail server.

And you will need a valid user in the current databse (or create your own with dbutil.py)
export TEST_USER_APIKEY=****
export TEST_USER_EMAIL=****
"""

# pylint: disable=too-many-lines
# pylint: disable=too-many-return-statements

import sys
import os
import logging
from urllib.parse import urlparse

import filetype
import bottle
from bottle import request

# Bottle creates a large number of no-member errors, so we just remove the warning
# pylint: disable=no-member
from lib.ctools import clogging

import wsgiserver               # pylint: disable=syntax-error
import db
import db_object
import auth
from auth import DEMO_MODE_AVAILABLE

from paths import view, STATIC_DIR
from constants import C,__version__,GET,GET_POST

import bottle_api
from bottle_api import git_head_time,git_last_commit,get_user_dict,fix_types
import dbmaint

DEFAULT_OFFSET = 0
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""
LOAD_MESSAGE = "Error: JavaScript did not execute. Please open JavaScript console and report a bug."

# Specify the base for the API and for the static files by Environment variables.
# This allows them to be served from different web servers.
# If they are not set, they default to '/' which is the same site that serves the HTML pages.
# STATIC is used to serve JavaScript
# API_BASE is used for the server API
api_base = os.getenv(C.PLANTTRACER_API_BASE,'/')
static_base = os.getenv(C.PLANTTRACER_STATIC_BASE,'/')


#############################################
### STARTUP CODE RUNS WHEN THIS IS LOADED ###
#############################################

app = bottle.default_app()      # for Lambda
app.mount('/api', bottle_api.api)

def fix_boto_log_level():
    for name in logging.root.manager.loggerDict:
        if name.startswith('boto'):
            logging.getLogger(name).setLevel(logging.INFO)

def startup():
    dbmaint.schema_upgrade(auth.get_dbwriter())
    clogging.setup(level=os.environ.get('PLANTTRACER_LOG_LEVEL',logging.INFO))
    fix_boto_log_level()
    config = auth.config()
    try:
        db_object.S3_BUCKET = config['s3']['s3_bucket']
    except KeyError as e:
        logging.info("s3_bucket not defined in config file. using db object store instead. %s",e)

if os.environ.get('AWS_LAMBDA',None)=='YES':
    startup()

################################################################
# Bottle endpoints


# Local Static

# Disable caching during development.
# https://stackoverflow.com/questions/24672996/python-bottle-and-cache-control
# "Note: If there is a Cache-Control header with the max-age or s-maxage directive in the response,
#  the Expires header is ignored."
# "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Expires
# Unfortunately, we are getting duplicate cache-control headers.
# So better to disable in the client:
# https://www.webinstinct.com/faq/how-to-disable-browser-cache


@bottle.route('/static/<path:path>', method=['GET'])
def static_path(path):
    full_path = os.path.join(STATIC_DIR,path)
    try:
        kind = filetype.guess(full_path)
    except FileNotFoundError as e:
        raise auth.http403(f'File not found: {full_path}') from e
    if kind is not None:
        mimetype = kind.mime
    elif path.endswith(".html"):
        mimetype = 'text/html'
    elif path.endswith(".js"):
        mimetype = 'text/javascript'
    else:
        mimetype = 'text/plain'
    response = bottle.static_file( path, root=STATIC_DIR, mimetype=mimetype )
    response.set_header('Cache-Control', 'public, max-age=5')
    return response

@bottle.route('/favicon.ico', method=['GET'])
def favicon():
    return static_path('favicon.ico')

################################################################
# HTML Pages served with template system
################################################################

def page_dict(title='', *, require_auth=False, lookup=True, logout=False,debug=False):
    """Returns a dictionary that can be used by post of the templates.
    :param: title - the title we should give the page
    :param: require_auth  - if true, the user must already be authenticated, or throws an error
    :param: logout - if true, force the user to log out by issuing a clear-cookie command
    :param: lookup - if true, we weren't being called in an error condition, so we can lookup the api_key in the URL or the cookie
    """
    logging.debug("1. page_dict require_auth=%s logout=%s lookup=%s",require_auth,logout,lookup)
    o = urlparse(request.url)
    logging.debug("o=%s",o)
    if lookup:
        api_key = auth.get_user_api_key()
        logging.debug("auth.get_user_api_key=%s",api_key)
        if api_key is None and require_auth is True:
            logging.debug("api_key is None and require_auth is True")
            raise auth.http403("api_key is None and require_auth is True")
    else:
        api_key = None

    if (api_key is not None) and (logout is False):
        # Get the user_dict is from the database
        user_dict = get_user_dict()
        user_name = user_dict['name']
        user_email = user_dict['email']
        user_demo  = user_dict['demo']
        user_id = user_dict['id']
        user_primary_course_id = user_dict['primary_course_id']
        logged_in = 1
        primary_course_name = db.lookup_course_by_id(course_id=user_primary_course_id)['course_name']
        admin = 1 if db.check_course_admin(user_id=user_id, course_id=user_primary_course_id) else 0
        # If this is a demo account, the user cannot be an admin (security)
        if user_demo:
            assert not admin
        # if this is not a demo account and the user_id is set, make sure we set the cookie
        if (user_id is not None) and (not user_demo):
            auth.set_cookie(api_key)

    else:
        user_name  = None
        user_email = None
        user_demo  = 0
        user_id    = None
        user_primary_course_id = None
        primary_course_name = None
        admin = 0
        logged_in = 0

    try:
        movie_id = int(request.query.get('movie_id'))
    except (AttributeError, KeyError, TypeError):
        movie_id = 0            # to avoid errors

    ret= fix_types({
        C.API_BASE: api_base,
        C.STATIC_BASE: static_base,
        'api_key': api_key,     # the API key that is currently active
        'user_id': user_id,     # the user_id that is active
        'user_name': user_name, # the user's name
        'user_email': user_email, # the user's email
        'user_demo':  user_demo,  # true if this is a demo user
        'logged_in': logged_in,
        'admin':admin,
        'user_primary_course_id': user_primary_course_id,
        'primary_course_name': primary_course_name,
        'title':'Plant Tracer '+title,
        'hostname':o.hostname,
        'movie_id':movie_id,
        'demo_mode_available':DEMO_MODE_AVAILABLE,
        'MAX_FILE_UPLOAD': C.MAX_FILE_UPLOAD,
        'dbreader_host':auth.get_dbreader().host,
        'version':__version__,
        'git_head_time':git_head_time(),
        'git_last_commit':git_last_commit()
    })
    for (k,v) in ret.items():
        if v is None:
            ret[k] = "null"
    if debug:
        logging.debug("fixed page_dict=%s",ret)
    return ret


@bottle.route('/', method=GET_POST)
@view('index.html')
def func_root():
    """/ - serve the home page"""
    logging.debug("func_root")
    ret = page_dict()
    return ret

@bottle.route('/about', method=GET_POST)
@view('about.html')
def func_about():
    return page_dict('About')

@bottle.route('/error', method=GET_POST)
@view('error.html')
def func_error():
    logging.debug("/error")
    auth.clear_cookie()
    return page_dict('Error', lookup=False)

@bottle.route('/audit', method=GET_POST)
@view('audit.html')
def func_audit():
    """/audit - view the audit logs"""
    return page_dict("Audit", require_auth=True)

@bottle.route('/list', method=GET_POST)
@view('list.html')
def func_list():
    """/list - list movies and edit them and user info"""
    logging.debug("/list")
    return page_dict('List Movies', require_auth=True)

@bottle.route('/analyze', method=GET_POST)
@view('analyze.html')
def func_analyze():
    """/analyze?movie_id=<movieid> - Analyze a movie, optionally annotating it."""
    return page_dict('Analyze Movie', require_auth=True)

##
## Login page includes the api keys of all the demo users.
##
@bottle.route('/login', method=GET_POST)
@view('login.html')
def func_login():
    return page_dict('Login')

@bottle.route('/logout', method=GET_POST)
@view('logout.html')
def func_logout():
    """/list - list movies and edit them and user info"""
    auth.clear_cookie()
    return page_dict('Logout',logout=True)

@bottle.route('/privacy', method=GET_POST)
@view('privacy.html')
def func_privacy():
    return page_dict('Privacy')

@bottle.route('/register', method=GET)
@view('register.html')
def func_register():
    """/register sends the register.html template which loads register.js with register variable set to True
     Note: register and resend both need the endpint so that they can post it to the server
     for inclusion in the email. This is the only place where the endpoint needs to be explicitly included.
    """
    o = urlparse(request.url)
    return {'title': 'Plant Tracer Registration Page',
            'hostname': o.hostname,
            'register': True
            }

@bottle.route('/resend', method=GET)
@view('register.html')
def func_resend():
    """/resend sends the register.html template which loads register.js with register variable set to False"""
    o = urlparse(request.url)
    return {'title': 'Plant Tracer Resend Registration Link',
            'hostname': o.hostname,
            'register': False
            }


@bottle.route('/tos', method=GET_POST)
@view('tos.html')
def func_tos():
    return page_dict('Terms of Service')

@bottle.route('/upload', method=GET_POST)
@view('upload.html')
def func_upload():
    """/upload - Upload a new file"""
    return page_dict('Upload a Movie', require_auth=True)

@bottle.route('/users', method=GET_POST)
@view('users.html')
def func_users():
    """/users - provide a users list"""
    return page_dict('List Users', require_auth=True)

################################################################
## debug/demo

@bottle.route('/demo_tracer1.html', method=GET)
@view('demo_tracer1.html')
def demo_tracer1():
    return page_dict('demo_tracer1',require_auth=False)

@bottle.route('/demo_tracer2.html', method=GET)
@view('demo_tracer2.html')
def demo_tracer2():
    return page_dict('demo_tracer2',require_auth=False)

@bottle.route('/demo_tracer3.html', method=GET)
@view('demo_tracer3.html')
def demo_tracer3():
    return page_dict('demo_tracer3',require_auth=False)

@bottle.route('/ver', method=GET_POST)
@view('version.txt')
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3.
    Run the dictionary below through the VERSION_TEAMPLTE with jinja2.
    """
    return {'__version__': __version__, 'sys_version': sys.version}

################################################################
# Bottle App
##


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--multi', help='Run multi-threaded server (no auto-reloader)', action='store_true')
    parser.add_argument('--storelocal', help='Store new objects locally, not in S3', action='store_true')
    parser.add_argument("--info", help='print info about the runtime environment', action='store_true')
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if C.PLANTTRACER_CREDENTIALS not in os.environ:
        print(f"Please define {C.PLANTTRACER_CREDENTIALS} and restart",file=sys.stderr)
        sys.exit(1)

    if args.info:
        for name in logging.root.manager.loggerDict:
            print("Logger: ",name)
        sys.exit(0)

    if args.storelocal:
        db_object.STORE_LOCAL=True

    # Now make sure that the credentials work
    # We only do this with the standalone program
    # the try/except is for when we run under a fixture in the pytest unit tests, which messes up ROOT_DIR
    try:
        from tests.dbreader_test import test_db_connection
        test_db_connection()
    except ModuleNotFoundError:
        pass

    startup()

    # Run the multi-threaded server? Needed for testing local-tracking
    if args.multi:
        httpd = wsgiserver.Server(app, listen='localhost', port=args.port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("")
            sys.exit(0)

    # Run the single-threaded server (more debugging and the reloader)
    bottle.default_app().run(host='localhost', debug=True, reloader=True, port=args.port)
