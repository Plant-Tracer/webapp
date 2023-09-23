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
export PLANTTRACER_ENDPOINT='http://localhost:8080' (or whatever it is printed above)
export SMTP_HOST=***
export SMTP_PASSWORD=***
export SMTP_PORT=***
export SMTP_USERNAME=***

For testing, you must also set:
export IMAP_PASSWORD=****
export IMAP_SERVER=****
export IMAP_USERNAME=****
export TEST_ENDPOINT='http://localhost:8080' (or whatever it is above)

And you will need a valid user in the current databse (or create your own with dbutil.py)
export TEST_USER_APIKEY=****
export TEST_USER_EMAIL=****
"""

import sys
import os
import io
import datetime
import logging
from urllib.parse import urlparse
import json

import mistune
import magic
import bottle
import base64
from bottle import request
from validate_email_address import validate_email

if mistune.__version__ < '3':
    raise RuntimeError("Please uninstall and reinstall mistune")

# pylint: disable=no-member

import db
from auth import get_user_api_key, get_user_ipaddr, get_movie_id, API_KEY_COOKIE_NAME
import paths
from paths import view,STATIC_DIR,TEMPLATE_DIR,PLANTTRACER_ENDPOINT
from lib.ctools import clogging

assert os.path.exists(TEMPLATE_DIR)


__version__='0.0.1'
VERSION_TEMPLATE='version.txt'

TOS_MD_FILE     = os.path.join(STATIC_DIR, 'tos.md')
PRIVACY_MD_FILE = os.path.join(STATIC_DIR, 'privacy.md')
PAGE_TEMPLATE   = 'page.html'
PAGE_STYLE = "<style>\ndiv.mypage { max-width: 600px;}\n</style>\n"

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""

MAX_FILE_UPLOAD = 1024*1024*16

INVALID_API_KEY      = {'error':True, 'message':'Invalid api_key'}
INVALID_EMAIL        = {'error':True, 'message':'Invalid email address'}
INVALID_MOVIE_ID     = {'error':True, 'message':'movie_id is invalid or missing'}
INVALID_MOVIE_ACCESS = {'error':True, 'message':'User does not have access to requested movie.'}
INVALID_COURSE_KEY   = {'error':True, 'message':'There is no course for that course key.'}
NO_REMAINING_REGISTRATIONS = {'error':True, 'message':'That course has no remaining registrations. Please contact your faculty member.'}
CHECK_MX = False                # True didn't work

def expand_memfile_max():
    logging.info("Changing MEMFILE_MAX from %d to %d",bottle.BaseRequest.MEMFILE_MAX, MAX_FILE_UPLOAD)
    bottle.BaseRequest.MEMFILE_MAX = MAX_FILE_UPLOAD


def datetime_to_str(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()  # or str(obj) if you prefer
    elif isinstance(obj, dict):
        return {k: datetime_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [datetime_to_str(elem) for elem in obj]
    else:
        return obj

################################################################
## Bottle endpoints


@bottle.route('/ver', method=['POST','GET'])
@view(VERSION_TEMPLATE)         # run the dictionary below through the VERSION_TEAMPLTE with jinja2
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3"""
    return {'__version__':__version__,'sys_version':sys.version}

@bottle.route('/tos', method=['GET'])
@view(PAGE_TEMPLATE)
def func_tos():
    """Fill the page template with the terms of service produced with markdown to HTML translation"""
    with open(TOS_MD_FILE,"r") as f:
        return {'page':mistune.html(f.read()), 'style':PAGE_STYLE }

@bottle.route('/privacy', method=['GET'])
@view(PAGE_TEMPLATE)
def func_privacy():
    """Fill the page template with the terms of service produced with markdown to HTML translation"""
    with open(PRIVACY_MD_FILE,"r") as f:
        return {'page':mistune.html(f.read()), 'style':PAGE_STYLE }

### Local Static

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
    response = bottle.static_file(path, root=STATIC_DIR, mimetype=magic.from_file(os.path.join(STATIC_DIR,path)))
    response.set_header('Cache-Control','public, max-age=5')
    return response

@bottle.route('/favicon.ico', method=['GET'])
def favicon():
    static_path('favicon.ico')

def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = get_user_api_key()
    if api_key is None:
        raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})
    userdict = db.validate_api_key( api_key )
    if not userdict:
        raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})
    return userdict

def get_user_id():
    """Returns the user_id of the currently logged in user, or throws a response"""
    userdict = get_user_dict()
    if 'id' in userdict:
        return userdict['id']
    logging.warning("no ID in userdict = %s",userdict)
    raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})


################################################################
### HTML Pages served with template system
################################################################

def page_dict():
    """Fill in data that goes to templates below and also set the cookie in a response"""
    api_key = get_user_api_key()
    if api_key is not None:
        bottle.response.set_cookie( API_KEY_COOKIE_NAME, api_key, path='/')
    user_dict  = get_user_dict( )
    user_id    = user_dict['id']
    user_primary_course_id   = user_dict['primary_course_id']
    course_dict = db.lookup_course(course_id = user_primary_course_id)
    return {'api_key':api_key,
            'user_id':user_id,
            'user_name':user_dict['name'],
            'user_email':user_dict['email'],
            'admin': db.check_course_admin( user_id, user_primary_course_id ),
            'user_primary_course_id':user_primary_course_id,
            'course_name':course_dict['course_name']}



@bottle.route('/', method=['GET'])
@view('index.html')
def func_root():
    """/ - serve the home page"""
    o = urlparse(request.url)
    return {'title':'Plant Tracer Launch Page',
            'hostname':o.hostname}

# Note: register and resend both need the endpint so that they can post it to the server
# for inclusion in the email. This is the only place where the endpoint needs to be explicitly included.
@bottle.route('/register', method=['GET'])
@view('register.html')
def func_register():
    """/register sends the register.html template which loads register.js with register variable set to True"""
    o = urlparse(request.url)
    return {'title':'Plant Tracer Registration Page',
            'hostname':o.hostname,
            'register':True,
            'planttracer_endpoint':PLANTTRACER_ENDPOINT
            }

@bottle.route('/resend', method=['GET'])
@view('register.html')
def func_resend():
    """/resend sends the register.html template which loads register.js with register variable set to False"""
    o = urlparse(request.url)
    return {'title':'Plant Tracer Resend Registration Link',
            'hostname':o.hostname,
            'register':False,
            'planttracer_endpoint':PLANTTRACER_ENDPOINT
            }


LOAD_MESSAGE="Error: JavaScript did not execute. Please open JavaScript console and report a bug."
@bottle.route('/list', method=['GET','POST'])
@view('list.html')
def func_list():
    """/list - list movies and edit them and user info"""
    return {**page_dict(),
            **{'title':'Plant Tracer List Movies',
               'load_message':LOAD_MESSAGE}}

@bottle.route('/upload', method=['GET','POST'])
@view('upload.html')
def func_upload():
    """/upload - Upload a new file"""
    return {**page_dict(),
            **{'title':'Plant Tracer Upload a Movie',
               'MAX_FILE_UPLOAD':MAX_FILE_UPLOAD}}

@bottle.route('/audit', method=['GET','POST'])
@view('audit.html')
def func_audit():
    """/audit - view the audit logs"""
    return {**page_dict(),
            **{'title':'Plant Tracer Audit'}}

@bottle.route('/users', method=['GET','POST'])
@view('users.html')
def func_users():
    """/users - provide a users list"""
    return {**page_dict(),
            **{'title':'Plant Tracer List Users'}}

################################################################
## /api URLs
################################################################

@bottle.route('/api/check-api_key', method=['GET','POST'])
def api_check_api_key( ):
    """API to check the user key and, if valid, return usedict or returns an error."""

    userdict = db.validate_api_key( get_user_api_key() )
    if userdict:
        return { 'error':False, 'userinfo': datetime_to_str( userdict ) }
    return INVALID_API_KEY


@bottle.route('/api/register', method=['GET','POST'])
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not validate_email(email, check_mx=False):
        logging.warning("email not valid: %s",email)
        return INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key( course_key ):
        return INVALID_COURSE_KEY
    if db.remaining_course_registrations( course_key ) < 1:
        return NO_REMAINING_REGISTRATIONS
    name = request.forms.get('name')
    db.register_email( email, course_key, name )
    db.send_links( email, planttracer_endpoint )
    return {'error':False, 'message':'Registration key sent to '+email}


@bottle.route('/api/resend-link', method=['GET','POST'])
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_endpoint = request.forms.get('planttracer_endpoint')
    if not validate_email(email, check_mx=CHECK_MX):
        logging.warning("email not valid: %s",email)
        return INVALID_EMAIL
    db.send_links( email, planttracer_endpoint )
    return {'error':False,'message':'If you have an account, a link was sent. If you do not receive a link within 60 seconds, you may need to <a href="/register">register</a> your email address.' }

##
## Movies
##

@bottle.route('/api/new-movie', method='POST')
def api_new_movie():
    """Creates a new movie for which we can upload frame-by-frame or all at once.
    :param api_key: the user's api_key
    :param title: The movie's title
    :param description: The movie's description
    :param movie: If present, the movie file
    """

    if 'movie' in request.files:
        with io.BytesIO() as f:
            request.files['movie'].save(f)
            movie_data = f.getvalue()
            if len(movie_data) > MAX_FILE_UPLOAD:
                return {'error':True, 'message':f'Upload larger than larger than {MAX_FILE_UPLOAD} bytes.'}
    else:
        movie_data = None


    movie_id = db.create_new_movie( get_user_id(),
                                    title = request.forms.get('title'),
                                    description = request.forms.get('description'),
                                    movie_data = movie_data
                                   )
    return {'error':False,'movie_id':movie_id}


@bottle.route('/api/new-frame', method='POST')
def api_new_frame():
    if db.can_access_movie( get_user_id(), request.forms.get('movie_id') ):
        frame_id = db.create_new_frame( request.forms.get('movie_id'),
                                        request.forms.get('frame_msec'),
                                        request.forms.get('frame_base64_data'))
        return {'error':False,'frame_id':frame_id}
    return INVALID_MOVIE_ACCESS

@bottle.route('/api/get-frame', method='POST')
def api_get_frame():
    """
    :param api_keuy:   authentication
    :param movie_id:   movie
    :param frame_msec: the frame specified
    :param msec_delta:      0 - this frame; +1 - next frame; -1 is previous frame
    """
    if db.can_access_movie( get_user_id(), request.forms.get('movie_id') ):
        return {'error':False, 'frame':db.get_frame( request.forms.get('movie_id'),
                                                      request.forms.get('frame_msec'),
                                                      request.forms.get('msec_delta')) }
    return INVALID_MOVIE_ACCESS

@bottle.route('/api/get-movie', method=['POST','GET'])
def api_get_movie():
    """
    :param api_keuy:   authentication
    :param movie_id:   movie
    """
    if db.can_access_movie( get_user_id(), get_movie_id()):
        bottle.response.set_header('Content-Type','video/quicktime')
        return db.get_movie( get_movie_id())
    return INVALID_MOVIE_ACCESS

@bottle.route('/api/delete-movie', method='POST')
def api_delete_movie():
    """ delete a movie
    :param movie_id: the id of the movie to delete
    :param delete: 1 (default) to delete the movie, 0 to undelete the movie.
    """
    if db.can_access_movie( get_user_id(), request.forms.get('movie_id')  ):
        db.delete_movie( request.forms.get('movie_id'), request.forms.get('delete',1) )
        return {'error':False}
    return INVALID_MOVIE_ACCESS

@bottle.route('/api/list-movies', method=['POST','GET'])
def api_list_movies():
    return {'error':False, 'movies': db.list_movies( get_user_id() ) }

##
## Metadata
##

def converter(x):
    if (x=='null') or (x is None):
        return None
    return int(x)


@bottle.route('/api/get-metadata', method='POST')
def api_get_metadata():
    get_movie_id = converter(request.forms.get('get_movie_id'))
    get_user_id  = converter(request.forms.get('get_user_id'))

    if (get_movie_id is None) and (get_user_id is None):
        return {'error':True, 'result':'Either get_movie_id or get_user_id is required'}

    return {'error':False, 'result':db.get_metadata( user_id=get_user_id(),
                                                     get_movie_id=get_movie_id,
                                                     get_user_id=get_user_id,
                                                     property=request.forms.get('property'),
                                                     value=request.forms.get('value') ) }

@bottle.route('/api/set-metadata', method='POST')
def api_set_metadata():
    """ set some aspect of the metadata
    :param api_key: authorization key
    :param movie_id: movie ID - if present, we are setting movie metadata
    :param user_id:  user ID  - if present, we are setting user metadata. (May not be the user_id from the api key)
    :param property: which piece of metadata to set
    :param value: what to set it to
    """
    logging.warning("request.forms=%s",list(request.forms.keys()))
    logging.warning("api_key=%s",request.forms.get('api_key'))
    logging.warning("get_user_id()=%s",get_user_id())

    set_movie_id = converter(request.forms.get('set_movie_id'))
    set_user_id  = converter(request.forms.get('set_user_id'))

    if (set_movie_id is None) and (set_user_id is None):
        return {'error':True, 'result':'Either set_movie_id or set_user_id is required'}

    result = db.set_metadata( user_id=get_user_id(),
                              set_movie_id=set_movie_id,
                              set_user_id=set_user_id,
                              property=request.forms.get('property'),
                              value=request.forms.get('value') )

    return {'error':False, 'result':result}


##
## Demo and debug
##
@bottle.route('/api/add', method=['GET','POST'])
def api_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True,'message':'arguments malformed'}

################################################################
## Bottle App
##

def app():
    """The application"""
    # Set up logging for a bottle app
    # https://stackoverflow.com/questions/2557168/how-do-i-change-the-default-format-of-log-messages-in-python-app-engine
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    #root.setLevel(logging.DEBUG)
    hdlr = root.handlers[0]
    fmt = logging.Formatter(clogging.LOG_FORMAT)
    hdlr.setFormatter(fmt)

    expand_memfile_max()
    return bottle.default_app()

if __name__=="__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Bottle App with Bottle's built-in server unless a command is given",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--dbcredentials',help='Specify .ini file with [dbreader] and [dbwriter] sections')
    parser.add_argument('--port',type=int)
    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.dbcredentials:
        if not os.path.exists(args.dbcredentials):
            raise FileNotFoundError(args.dbcredentials)
        paths.BOTTLE_APP_INI = args.dbcredentials
    bottle.default_app().run(host='localhost',debug=True, reloader=True, port=args.port)
