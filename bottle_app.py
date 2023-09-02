"""
WSGI file used for bottle interface.

The goal is to only have the bottle code in this file and nowhere else.

Debug on Dreamhost:
(cd ~/apps.digitalcorpora.org/;make touch)
https://downloads.digitalcorpora.org/
https://downloads.digitalcorpora.org/ver
https://downloads.digitalcorpora.org/reports

Debug locally:

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

# pylint: disable=no-member


import db
from paths import STATIC_DIR,TEMPLATE_DIR,view,PLANTTRACER_API_ENDPOINT,PLANTTRACER_HTML_ENDPOINT
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

## TEMPLATE VIEWS
@bottle.route('/', method=['GET'])
@view('index.html')
def func_root():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname}

@bottle.route('/register', method=['GET'])
@view('register.html')
def func_register():
    """/register sends the register.html template which loads register.js with register variable set to True"""
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':True,
            'planttracer_html_endpoint':PLANTTRACER_HTML_ENDPOINT
            }

@bottle.route('/resend', method=['GET'])
@view('register.html')
def func_resend():
    """/resend sends the register.html template which loads register.js with register variable set to False"""
    logging.warning("endpoint=%s",PLANTTRACER_API_ENDPOINT);
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':False,
            'planttracer_html_endpoint':PLANTTRACER_HTML_ENDPOINT
            }


@bottle.route('/list', method=['GET'])
@view('list.html')
def func_list():
    """list movies and edit them and user info"""
    api_key = get_user_api_key()
    user_dict = get_user_dict( )
    return {'title':'Plant Tracer List, Edit and Play',
            'api_key':api_key,
            'user_id':user_dict['id'],
            'admin':False,
            'user_primary_course_id':user_dict['primary_course_id'],
            'planttracer_api_endpoint':PLANTTRACER_API_ENDPOINT
            }


@bottle.route('/upload', method=['GET'])
@view('upload.html')
def func_upload():
    """Upload a new file"""
    api_key = get_user_api_key()
    user_id = get_user_id ( )
    return {'title':'Plant Tracer List, Edit and Play',
            'api_key':api_key,
            'user_id':user_id,
            'MAX_FILE_UPLOAD':MAX_FILE_UPLOAD,
            'planttracer_api_endpoint':PLANTTRACER_API_ENDPOINT
            }



################################################################
## API

def get_user_api_key():
    """Gets the user APIkey from either the URL or the cookie or the form.
    :return: None if user is not logged in
    """


    # check the query string
    api_key = request.query.get('api_key',None)
    if api_key:
        return api_key
    # check for a form submission
    api_key = request.forms.get('api_key',None)
    if api_key:
        return api_key
    # Check for a cookie
    api_key = request.get_cookie('api_key',None)
    if api_key:
        return api_key
    return None



def get_user_dict():
    """Returns the user_id of the currently logged in user, or throws a response"""
    api_key = get_user_api_key()
    if api_key is None:
        raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})
    userdict = db.validate_api_key( api_key )
    return userdict

def get_user_id():
    """Returns the user_id of the currently logged in user, or throws a response"""
    userdict = get_user_dict()
    if 'id' in userdict:
        return userdict['id']
    logging.warning("no ID in userdict = %s",userdict)
    raise bottle.HTTPResponse(body=json.dumps(INVALID_API_KEY), status=200, headers={'Content-type':'application/json'})


@bottle.route('/api/check-api_key', method=['GET','POST'])
def api_check_api_key( ):
    userdict = db.validate_api_key( request.forms.get('api_key') )
    if userdict:
        return { 'error':False, 'userinfo': datetime_to_str( userdict ) }
    return INVALID_API_KEY


################################################################
## Registration
@bottle.route('/api/register', method=['GET','POST'])
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_html_endpoint = request.forms.get('planttracer_html_endpoint')
    if not validate_email(email, check_mx=True):
        logging.warning("email not valid: %s",email)
        return INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not db.validate_course_key( course_key ):
        return INVALID_COURSE_KEY
    if db.remaining_course_registrations( course_key ) < 1:
        return NO_REMAINING_REGISTRATIONS
    db.register_email( email, course_key )
    db.send_links( email, planttracer_html_endpoint )
    return {'error':False}


@bottle.route('/api/resend-link', method=['GET','POST'])
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    planttracer_html_endpoint = request.forms.get('planttracer_html_endpoint')
    if not validate_email(email, check_mx=CHECK_MX):
        logging.warning("email not valid: %s",email)
        return INVALID_EMAIL
    db.send_links( email, planttracer_html_endpoint )
    return {'error':False,'message':'If you have an account, a link was sent.' }

################################################################
## Movies
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

@bottle.route('/api/set-movie-metadata', method='POST')
def api_set_movie_metadata():
    """ set some aspect of the movie's metadata
    :param api_key: authorization key
    :param movie_id: movie ID
    :param property: which piece of metadata to set
    :param value: what to set it to
    """
    logging.warning("request.forms=%s",list(request.forms.keys()))
    logging.warning("api_key=%s",request.forms.get('api_key'))
    logging.warning("get_user_id()=%s",get_user_id())

    result = db.set_movie_metadata( get_user_id(),
                                    int(request.forms.get('movie_id')),
                                    request.forms.get('property'),
                                    request.forms.get('value') )

    return {'error':False, 'result':result}


################################################################
## Demo and debug
@bottle.route('/api/add', method=['GET','POST'])
def api_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True,'message':'arguments malformed'}

################################################################
## App


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
    parser.add_argument("--sendlink",help="send link to the given email address, registering it if necessary.")

    clogging.add_argument(parser, loglevel_default='WARNING')
    args = parser.parse_args()
    clogging.setup(level=args.loglevel)

    if args.sendlink:
        db.send_links( args.sendlink )
        sys.exit(0)

    bottle.default_app().run(host='localhost',debug=True, reloader=True)
