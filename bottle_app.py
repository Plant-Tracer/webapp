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
from urllib.parse import urlparse

import magic
import bottle
from bottle import request

# pylint: disable=no-member


from paths import STATIC_DIR,TEMPLATE_DIR,DBREADER_BASH_FILE,DBWRITER_BASH_FILE,view
from lib.ctools import dbfile

assert os.path.exists(TEMPLATE_DIR)

__version__='0.0.1'
VERSION_TEMPLATE='version.txt'

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000

INVALID_APIKEY = {'error':True, 'message':'Invalid apikey'}
INVALID_MOVIE_ACCESS = {'error':True, 'message':'User does not have access to requested movie'}

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

## API Validation
def validate_apikey():
    res = dbfile.DBMySQL.csfr( get_dbwriter(), "SELECT user_id from api_keys where key_value=%s limit 1",
                                    ( request.forms.get('apikey'), ), asDicts=True)
    if res:
        return res[0]['user_id']
    return None


@bottle.route('/api/check-apikey', method='POST')
def func_check_apikey():
    res = dbfile.DBMySQL.csfr( get_dbwriter(),
                               "SELECT * from api_keys left join users on user_id=users.id where key_value=%s",
                               (request.forms.get('apikey'), ), asDicts=True)
    if res:
        return { 'error':False, 'userinfo': datetime_to_str(res[0]) }
    return INVALID_APIKEY



## Movies API
@bottle.route('/api/new-movie', method='POST')
def func_new_movie():
    apikey_userid = validate_apikey()
    if apikey_userid:
        movie_id = dbfile.DBMySQL.csfr( get_dbwriter(),
                                            "INSERT INTO movies (title,description,user_id) VALUES (%s,%s,%s)",
                                            (request.forms.get('title'), request.forms.get('description'), apikey_userid ))
        return {'error':False,'movie_id':movie_id}
    return INVALID_APIKEY

@bottle.route('/api/new-frame', method='POST')
def func_new_frame():
    apikey_userid = validate_apikey()
    if apikey_userid:
        res = dbfile.DBMySQL.csfr( get_dbreader(), "SELECT user_id from movies where id=%s",
                                       ( int(request.forms.get('movie_id')), ),
                                       asDicts=True)
        if apikey_userid != res[0]['user_id']:
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
    return INVALID_APIKEY




## Demo API
@bottle.route('/api/add', method='POST')
def func_add():
    a = request.forms.get('a')
    b = request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True}



def app():
    """The application"""
    return bottle.default_app()

if __name__=="__main__":
    bottle.default_app().run(host='localhost',debug=True, reloader=True)
