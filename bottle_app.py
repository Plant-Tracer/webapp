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
from urllib.parse import urlparse

import magic
import bottle
from bottle import request

from paths import STATIC_DIR,TEMPLATE_DIR,DBREADER_BASH_FILE,view
from lib.ctools import dbfile

assert os.path.exists(TEMPLATE_DIR)

__version__='0.0.1'
VERSION_TEMPLATE='version.txt'

DEFAULT_OFFSET = 0
DEFAULT_ROW_COUNT = 1000000
DEFAULT_SEARCH_ROW_COUNT = 1000

@functools.cache
def get_dbreader():
    """Get the dbreader authentication info from the DBREADER_BASH_FILE if it exists. Variables there are
    shadowed by environment variables MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
    If the file doesn't exist, send in None, hoping that the environment variables exist."""
    fname = DBREADER_BASH_FILE if os.path.exists(DBREADER_BASH_FILE) else None
    return dbfile.DBMySQLAuth.FromBashEnvFile( fname )

@bottle.route('/ver')
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
    o = urlparse(bottle.request.url)
    return {'title':'ROOT',
            'hostname':o.hostname}

## Demo API
@bottle.route('/api/add', method='POST')
def func_add():
    a = bottle.request.forms.get('a')
    b = bottle.request.forms.get('b')
    try:
        return {'result':float(a)+float(b), 'error':False}
    except (TypeError,ValueError):
        return {'error':True}

def app():
    """The application"""
    return bottle.default_app()

if __name__=="__main__":
    bottle.default_app().run(host='localhost',debug=True, reloader=True)
