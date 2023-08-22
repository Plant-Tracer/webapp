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
import functools
import datetime
import base64
import uuid
import logging
from urllib.parse import urlparse

import magic
import bottle
from bottle import request
from validate_email_address import validate_email

# pylint: disable=no-member


from paths import STATIC_DIR,TEMPLATE_DIR,DBREADER_BASH_FILE,DBWRITER_BASH_FILE,view
from lib.ctools import dbfile
from lib.ctools import clogging

assert os.path.exists(TEMPLATE_DIR)

__version__='0.0.1'
VERSION_TEMPLATE='version.txt'

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000
MIN_SEND_INTERVAL = 60
DEFAULT_CAPABILITIES = ""

INVALID_API_KEY = {'error':True, 'message':'Invalid api_key'}
INVALID_EMAIL  = {'error':True, 'message':'Invalid email address'}
INVALID_MOVIE_ACCESS = {'error':True, 'message':'User does not have access to requested movie.'}
INVALID_COURSE_KEY = {'error':True, 'message':'There is no course for that course key.'}
NO_REMAINING_REGISTRATIONS = {'error':True, 'message':'That course has no remaining registrations. Please contact your faculty member.'}

class InvalidEmail(RuntimeError):
    """Exception thrown in email is invalid"""

class InvalidApi_Key(RuntimeError):
    """ API Key is invalid """

def datetime_to_str(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()  # or str(obj) if you prefer
    elif isinstance(obj, dict):
        return {k: datetime_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [datetime_to_str(elem) for elem in obj]
    else:
        return obj

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from the DBREADER_BASH_FILE if it exists. Variables there are
    shadowed by environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    If the file doesn't exist, send in None, hoping that the environment variables exist."""
    fname = DBREADER_BASH_FILE if os.path.exists(DBREADER_BASH_FILE) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile( fname )

@functools.cache
def get_dbwriter():
    """Get the dbwriter authentication info from the DBWRITER_BASH_FILE if it exists. Variables there are
    shadowed by environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    If the file doesn't exist, send in None, hoping that the environment variables exist."""
    fname = DBWRITER_BASH_FILE if os.path.exists(DBWRITER_BASH_FILE) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile( fname )

################################################################
## database utility functions

def create_course(course_key, course_name, max_enrollment):
    """Create a new course
    :return: course_id of the new course
    """
    return dbfile.DBMySQL.csfr( get_dbwriter(), "INSERT into courses (course_key, course_name, max_enrollment) values (%s,%s,%s)",
                                (course_key, course_name, max_enrollment))

def delete_course(course_key):
    """Delete a course.
    :return: number of courses deleted.
    """
    return dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from courses where course_key=%s", (course_key,))

##
def register_email(email, course_key):
    """Register email for a given course
    :param: email - user email
    :param: course_key - the key
    :return: the number of users registered
    """

    CHECK_MX = False            # True doesn't work
    if not validate_email(email, check_mx=CHECK_MX):
        raise InvalidEmail( email )
    return dbfile.DBMySQL.csfr( get_dbwriter(),
                         "INSERT into users (email, course_key) VALUES (%s, %s) ON DUPLICATE KEY UPDATE email=%s,course_key=%s",
                         ( email, course_key, email, course_key ))

def rename_user(user_id, old_email, new_email):
    """Changes a user's email. Requires a correct old_email"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "UPDATE users set email=%s where id=%s and email=%s",
                         ( old_email, user_id, new_email))

def delete_user(email):
    """Delete a user. A course cannot be deleted if it has any users. A user cannot be deleted if it has any movies"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from users where email=%s", (email,))

def delete_movie(movie_id):
    """Delete a movie and all its frames"""
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from frames where movie_id=%s", (movie_id,))
    dbfile.DBMySQL.csfr( get_dbwriter(), "DELETE from movies where movie_id=%s", (movie_id,))

def new_api_key(email, *, capabilities=DEFAULT_CAPABILITIES):
    """Create a new api_key for an email that is registered
    :param: email - the email
    :return: api_key - the api_key
    """
    api_key = str(uuid.uuid4()).replace('-','')
    dbfile.DBMySQL.csfr( get_dbwriter(),
                         """INSERT into api_keys (user_id, api_key, capabilities)
                            VALUES ((select id from users where email=%s), %s, %s)""",
                         (email, api_key, capabilities), debug=True)
    return api_key

def delete_api_key(api_key):
    """Deletes an api_key
    :param: api_key - the api_key
    :return: the number of keys deleted
    """
    return dbfile.DBMySQL.csfr( get_dbwriter(),
                                """DELETE from api_keys WHERE api_key=%s""",
                                (api_key,))

def send_links(email):
    """Send the links to the email address if they haven't been sent for MIN_SEND_INTERVAL"""
    raise RuntimeError("implement send_links")

def validate_course_key( course_key ):
    res = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT course_key from courses where course_key=%s LIMIT 1""", (course_key,))
    return len(res)==1 and res[0][0]==course_key

def remaining_course_registrations( course_key ):
    res = dbfile.DBMySQL.csfr(get_dbreader(),
                              """SELECT max_enrollment - (select count(*) from users where course_key=%s) from courses where course_key=%s""",
                              (course_key,course_key))
    try:
        return int(res[0][0])
    except (IndexError,ValueError):
        return 0

################################################################
## Bottle endpoints


@bottle.route('/ver', method=['POST','GET'])
@view(VERSION_TEMPLATE)
def func_ver():
    """Demo for reporting python version. Allows us to validate we are using Python3"""
    return {'__version__':__version__,'sys_version':sys.version}

### Local Static
@bottle.get('/static/<path:path>')
def static_path(path):
    return bottle.static_file(path, root=STATIC_DIR, mimetype=magic.from_file(os.path.join(STATIC_DIR,path)))

## TEMPLATE VIEWS
@bottle.route('/')
@view('index.html')
def func_root():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname}

@bottle.route('/register')
@view('register.html')
def func_register():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':True
            }

@bottle.route('/resend')
@view('register.html')
def func_resend():
    o = urlparse(request.url)
    return {'title':'ROOT',
            'hostname':o.hostname,
            'register':False
            }


## API Validation
def validate_api_key():
    res = dbfile.DBMySQL.csfr( get_dbwriter(), "SELECT user_id from api_keys where api_key=%s limit 1",
                                    ( request.forms.get('api_key'), ), asDicts=True)
    if res:
        return res[0]['user_id']
    return None


@bottle.route('/api/check-api_key', method='POST')
def api_check_api_key():
    api_key = str(request.forms.get('api_key'))
    res = dbfile.DBMySQL.csfr( get_dbwriter(),
                               "SELECT * from api_keys left join users on user_id=users.id where api_key=%s",
                               (api_key, ), asDicts=True)
    logging.info("api_key[0:9]=%s res=%s",api_key[0:9], res)
    if res:
        return { 'error':False, 'userinfo': datetime_to_str(res[0]) }
    return INVALID_API_KEY


## Movies API
@bottle.route('/api/register', method='POST')
def api_register():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    if not validate_email(email, check_mx=True):
        return INVALID_EMAIL
    course_key = request.forms.get('course_key')
    if not validate_course_key(course_key):
        return INVALID_COURSE_KEY
    if remaining_course_registrations(course_key) < 1:
        return NO_REMAINING_REGISTRATIONS
    register_email(email, course_key)
    send_links(email)
    return {'error':False}


@bottle.route('/api/resend-link', method='POST')
def api_send_link():
    """Register the email address if it does not exist. Send a login and upload link"""
    email = request.forms.get('email')
    if not validate_email(email, check_mx=True):
        return INVALID_EMAIL
    send_links(email)
    return {'error':False}


@bottle.route('/api/new-movie', method='POST')
def api_new_movie():
    api_key_userid = validate_api_key()
    if api_key_userid:
        movie_id = dbfile.DBMySQL.csfr( get_dbwriter(),
                                            "INSERT INTO movies (title,description,user_id) VALUES (%s,%s,%s)",
                                            (request.forms.get('title'), request.forms.get('description'), api_key_userid ))
        return {'error':False,'movie_id':movie_id}
    return INVALID_API_KEY

@bottle.route('/api/new-frame', method='POST')
def api_new_frame():
    api_key_userid = validate_api_key()
    if api_key_userid:
        res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT user_id from movies where id=%s",
                                       ( int(request.forms.get('movie_id')), ),
                                       asDicts=True)
        if api_key_userid != res[0]['user_id']:
            return INVALID_MOVIE_ACCESS

        frame_data = base64.b64decode(request.forms.get('frame_base64_data'))
        frame_id = dbfile.DBMySQL.csfr( get_dbwriter(),
                                        """INSERT INTO frames (movie_id,frame_number,frame_msec,frame_data)
                                           VALUES (%s,%s,%s,%s)
                                           ON DUPLICATE KEY UPDATE frame_msec=%s,frame_data=%s""",
                                            (
                                                int(request.forms.get('movie_id')),
                                            int(request.forms.get('frame_number')),
                                            int(request.forms.get('frame_msec')),
                                            frame_data,
                                            int(request.forms.get('frame_msec')),
                                            frame_data),
                                            debug=False)


        return {'error':False,'frame_id':frame_id}
    return INVALID_API_KEY


## Demo API
@bottle.route('/api/add', method='POST')
def api_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True}

def app():
    """The application"""
    # Set up logging for a bottle app
    # https://stackoverflow.com/questions/2557168/how-do-i-change-the-default-format-of-log-messages-in-python-app-engine
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    hdlr = root.handlers[0]
    fmt = logging.Formatter(clogging.LOG_FORMAT)
    hdlr.setFormatter(fmt)
    return bottle.default_app()

if __name__=="__main__":
    bottle.default_app().run(host='localhost',debug=True, reloader=True)
