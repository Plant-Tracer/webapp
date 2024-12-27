"""
Main Flask application for planttracer.
"""

# pylint: disable=too-many-lines
# pylint: disable=too-many-return-statements

import sys
import os
import logging

from flask import Flask, request, render_template, jsonify, make_response

# Bottle creates a large number of no-member errors, so we just remove the warning
# pylint: disable=no-member
from . import auth
from . import db_object
from . import dbmaint
from . import clogging

from .bottle_api import api_bp
from .constants import __version__,GET,GET_POST
from .auth import AuthError
from .apikey import cookie_name, page_dict

DEFAULT_OFFSET = 0
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""
LOAD_MESSAGE = "Error: JavaScript did not execute. Please open JavaScript console and report a bug."
CACHE_MAX_AGE = 5               # for debugging; change to 360 for production

################################################################
# Initialization Code

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
## API SUPPORT

app = Flask(__name__)
app.register_blueprint(api_bp, url_prefix='/api')

# Note - Flask automatically serves /static

## Error handling

@app.errorhandler(AuthError)
def handle_auth_error(ex):
    """Raise AuthError('message') will result in a JSON response:
    {'message':message, 'error':True}
    as defined in auth.AuthError
    """
    response = jsonify(ex.to_dict())
    response.status_code = ex.status_code
    return response

################################################################
# HTML Pages served with template system
################################################################

@app.route('/', methods=GET)
def func_root():
    """/ - serve the home page"""
    return render_template('index.html', **page_dict())

@app.route('/about', methods=GET)
def func_about():
    return render_template('about.html', **page_dict('About'))

@app.route('/error', methods=GET)
def func_error():
    return render_template('error.html', **page_dict('Error', lookup=False))

@app.route('/audit', methods=GET)
def func_audit():
    return render_template('audit.html', **page_dict("Audit", require_auth=True))

@app.route('/list', methods=GET)
def func_list():
    return render_template('list.html', **page_dict('List Movies', require_auth=True))

@app.route('/analyze', methods=GET)
def func_analyze():
    return render_template('analyze.html', **page_dict('Analyze Movie', require_auth=True))

## debug page
@app.route('/debug', methods=GET)
def app_debug():
    return render_template('debug.html', routes=app.url_map)

##
## Login page includes the api keys of all the demo users.
##
@app.route('/login', methods=GET_POST)
def func_login():
    return render_template('login.html', **page_dict('Login'))

@app.route('/logout', methods=GET_POST)
def func_logout():
    resp = render_template('logout.html', **page_dict('Logout',logout=True))
    resp.set_cookie(cookie_name(), '', expires=0)
    return resp

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

@app.route('/upload', methods=GET)
def func_upload():
    """/upload - Upload a new file"""
    return render_template('upload.html', **page_dict('Upload a Movie', require_auth=True))

@app.route('/users', methods=GET)
def func_users():
    """/users - provide a users list"""
    return render_template('users.html', **page_dict('List Users', require_auth=True))

################################################################
## debug/demo

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
    response = make_response(render_template('version.txt',
                                             __version__=__version__,
                                             sys_version= sys.version))
    response.headers['Content-Type'] = 'text/plain'
    return response
